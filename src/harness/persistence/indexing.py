"""Rebuild the SQLite index by scanning authoritative ``runs/`` artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.media.isaac_export import export_isaac_replay
from harness.media.reactor_media import normalize_reactor_media
from harness.persistence.store import ExperimentStore


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _created_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def _artifact_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".npy": return "raw_sensor_frame"
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}: return "image"
    if suffix in {".mp4", ".webm", ".mov"}: return "video"
    if suffix == ".json": return "metadata"
    if suffix == ".jsonl": return "trajectory"
    return "artifact"


def _resolve_ref(value: str, project_root: Path) -> Path:
    path = Path(value)
    if path.exists(): return path
    prefix = Path("/workspace/project")
    try:
        return project_root / path.relative_to(prefix)
    except ValueError:
        return project_root / path if not path.is_absolute() else path


def _run_artifacts(run_directory: Path, project_root: Path) -> list[tuple[str, Path, dict[str, Any]]]:
    artifacts: list[tuple[str, Path, dict[str, Any]]] = []
    for path in run_directory.rglob("*"):
        if path.is_file() and path.name not in {"scenario.json", "metadata.json", "result.json"}:
            artifacts.append((_artifact_kind(path), path, {}))
    trajectory = run_directory / "trajectory.jsonl"
    if trajectory.exists():
        for line in trajectory.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            for observation in (entry.get("observation", {}), entry.get("result", {}).get("observation", {})):
                for ref in observation.get("sensor_refs", []):
                    path = _resolve_ref(ref, project_root)
                    if path.is_file() and all(existing[1] != path for existing in artifacts):
                        artifacts.append((_artifact_kind(path), path, {}))
    return artifacts


def _record_from_run(run_directory: Path) -> dict[str, Any] | None:
    scenario_path, metadata_path, result_path = (run_directory / "scenario.json", run_directory / "metadata.json", run_directory / "result.json")
    if not scenario_path.exists() or not metadata_path.exists() or not result_path.exists():
        return None
    scenario, metadata, evaluation = _read_json(scenario_path), _read_json(metadata_path), _read_json(result_path)
    return {
        "run_id": metadata["run_id"], "backend": metadata["backend"], "scenario": scenario,
        "trajectory_ref": str(run_directory / "trajectory.jsonl"), "evaluation": evaluation,
        "created_at": _created_at(result_path),
    }


def _index_pair(store: ExperimentStore, comparison_path: Path, project_root: Path) -> tuple[int, int]:
    payload = _read_json(comparison_path)
    matched = payload["matched_experiment"]
    count = 0
    for record in (matched["isaac_record"], matched["neural_record"]):
        trajectory = _resolve_ref(record["trajectory_ref"], project_root)
        store.upsert_experiment(record, run_directory=trajectory.parent)
        refs = list(record["evaluation"].get("evidence_refs", [])) + [record["trajectory_ref"]]
        artifacts = [(_artifact_kind(_resolve_ref(ref, project_root)), _resolve_ref(ref, project_root), {}) for ref in refs]
        if record["backend"] == "isaac_sim":
            run_artifacts = _run_artifacts(trajectory.parent, project_root)
            artifacts.extend(run_artifacts)
            if any(kind == "raw_sensor_frame" for kind, _, _ in run_artifacts):
                replay = export_isaac_replay(trajectory.parent)
                artifacts.extend([
                    ("video", Path(replay["video_path"]), {"derived_from": "raw_sensor_frame"}),
                    ("thumbnail", Path(replay["thumbnail_path"]), {"derived_from": "raw_sensor_frame"}),
                    ("media_manifest", Path(replay["manifest_path"]), {"derived_from": "raw_sensor_frame"}),
                ])
        store.replace_artifacts("experiment", record["run_id"], artifacts)
        count += 1
    store.upsert_pair(payload, comparison_path, created_at=_created_at(comparison_path))
    pair_id = payload["comparison"]["pair_id"]
    refs = list(payload["comparison"].get("evidence_refs", [])) + [str(comparison_path)]
    store.replace_artifacts(
        "pair", pair_id,
        [(_artifact_kind(_resolve_ref(ref, project_root)), _resolve_ref(ref, project_root), {}) for ref in refs],
    )
    return count, 1


def reindex_runs(store: ExperimentStore, runs_root: str | Path) -> dict[str, int]:
    """Scan ``runs/`` and repopulate/upsert its compact metadata index."""
    runs_root = Path(runs_root).resolve()
    project_root = runs_root.parent
    experiments = pairs = 0
    paired_paths = set(runs_root.glob("paired/*/comparison.json"))
    for comparison_path in sorted(paired_paths):
        indexed, pair_count = _index_pair(store, comparison_path, project_root)
        experiments += indexed; pairs += pair_count
    for scenario_path in sorted(runs_root.rglob("scenario.json")):
        run_directory = scenario_path.parent
        if "paired" in run_directory.parts:
            continue
        record = _record_from_run(run_directory)
        if record is None:
            continue
        store.upsert_experiment(record, run_directory=run_directory, result_path=run_directory / "result.json")
        artifacts = _run_artifacts(run_directory, project_root)
        if record["backend"] == "isaac_sim":
            raw_frames = [path for kind, path, _ in artifacts if kind == "raw_sensor_frame"]
            if raw_frames:
                replay = export_isaac_replay(run_directory)
                artifacts.extend([
                    ("video", Path(replay["video_path"]), {"derived_from": "raw_sensor_frame"}),
                    ("thumbnail", Path(replay["thumbnail_path"]), {"derived_from": "raw_sensor_frame"}),
                    ("media_manifest", Path(replay["manifest_path"]), {"derived_from": "raw_sensor_frame"}),
                ])
        store.replace_artifacts("experiment", record["run_id"], artifacts)
        experiments += 1
    for pair in store.list_pairs():
        reactor = store.get_experiment(pair["reactor_run_id"])
        if reactor and reactor["run_directory"]:
            normalized = normalize_reactor_media(reactor["run_directory"], [item["path"] for item in store.artifacts_for("experiment", reactor["run_id"])])
            store.register_artifact("experiment", reactor["run_id"], "thumbnail", normalized["thumbnail_path"], {"derived_from": "reactor_visual_evidence"}) if normalized["thumbnail_path"] else None
            store.register_artifact("experiment", reactor["run_id"], "media_manifest", normalized["manifest_path"], {"native_metadata_path": normalized["native_metadata_path"]})
    return {"experiments": experiments, "pairs": pairs}
