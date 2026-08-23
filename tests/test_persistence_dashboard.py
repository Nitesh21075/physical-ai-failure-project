import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from harness.dashboard.app import create_app
from harness.media import export_isaac_replay, normalize_reactor_media
from harness.persistence import ExperimentStore, ReviewState, reindex_runs


def _comparison_payload(root: Path) -> dict:
    isaac_dir = root / "isaac" / "run-isaac"
    reactor_dir = root / "reactor"
    isaac_dir.mkdir(parents=True)
    reactor_dir.mkdir()
    trajectory = isaac_dir / "trajectory.jsonl"
    trajectory.write_text(
        json.dumps({"record_type": "initial_observation", "observation": {"simulation_time": 0}})
        + "\n"
        + json.dumps({"record_type": "step", "action": {"name": "move"}, "result": {"simulation_time": 1, "done": True, "events": [{"event_type": "structural_collapse"}]}})
        + "\n",
        encoding="utf-8",
    )
    frame = reactor_dir / "frame.png"
    Image.new("RGB", (16, 12), "black").save(frame)
    scenario = {"scenario_id": "scenario-1", "task": "reach", "seed": 4, "parameters": {}, "hazards": {}}
    return {
        "matched_experiment": {
            "specification": {"pair_id": "pair-1", "task": "reach", "seed": 4, "action_alignment": "semantic", "alignment_note": "visual steering", "isaac_scenario": {**scenario, "environment": "isaac_sim"}, "neural_scenario": {**scenario, "environment": "reactor/lingbot-world-2"}},
            "isaac_record": {"run_id": "isaac-1", "backend": "isaac_sim", "scenario": {**scenario, "environment": "isaac_sim"}, "trajectory_ref": str(trajectory), "created_at": "2026-01-01T00:00:00+00:00", "evaluation": {"task_success": False, "environmental_failure": True, "failure_type": "structural_collapse", "severity": "high", "terminal": True}},
            "neural_record": {"run_id": "reactor-1", "backend": "reactor/lingbot-world-2", "scenario": {**scenario, "environment": "reactor/lingbot-world-2"}, "trajectory_ref": str(reactor_dir / "summary.json"), "created_at": "2026-01-01T00:00:00+00:00", "evaluation": {"task_success": False, "environmental_failure": False, "failure_type": None, "severity": "none", "terminal": False, "evidence_refs": [str(frame)]}},
        },
        "comparison": {"pair_id": "pair-1", "status": "inconclusive", "action_alignment": "semantic", "physics_environmental_failure": True, "physics_failure_type": "structural_collapse", "reason": "no decision", "evidence_refs": [], "visual_assessment": {"event_type": "structural_collapse", "observed": None, "confidence": 0.0, "assessor": "reviewer", "evidence_refs": []}},
    }


def test_store_persists_pair_review_and_dashboard_view(tmp_path: Path):
    store = ExperimentStore(tmp_path / "experiments.sqlite3")
    payload = _comparison_payload(tmp_path)
    for record in (payload["matched_experiment"]["isaac_record"], payload["matched_experiment"]["neural_record"]):
        store.upsert_experiment(record, run_directory=Path(record["trajectory_ref"]).parent)
    comparison = tmp_path / "comparison.json"
    comparison.write_text(json.dumps(payload), encoding="utf-8")
    store.upsert_pair(payload, comparison)
    store.register_artifact("experiment", "reactor-1", "image", tmp_path / "reactor" / "frame.png")
    store.set_review_state("pair-1", ReviewState.INCONCLUSIVE)

    client = TestClient(create_app(store))
    assert client.get("/api/pairs").json()[0]["review_state"] == "inconclusive"
    detail = client.get("/api/pairs/pair-1").json()
    assert detail["authority"]["isaac"] == "PHYSICS-GROUNDED SIMULATION"
    assert detail["isaac_timeline"][-1]["kind"] == "termination"
    pair_page = client.get("/pairs/pair-1")
    assert pair_page.status_code == 200
    assert "Physics-grounded simulation — reference" in pair_page.text
    assert "Neural-world visual evidence — not physics ground truth" in pair_page.text
    assert "<details>" in pair_page.text
    assert client.get("/api/experiments/isaac-1").json()["authority"] == "PHYSICS-GROUNDED SIMULATION"
    assert client.put("/api/pairs/pair-1/review", json={"review_state": "valid_discrepancy"}).status_code == 200


def test_reindex_rebuilds_standard_and_paired_run_index(tmp_path: Path):
    runs = tmp_path / "runs"
    run_dir = runs / "isaac-batch" / "run-1"
    camera_dir = runs / "isaac-batch" / "camera" / "hash"
    run_dir.mkdir(parents=True); camera_dir.mkdir(parents=True)
    (run_dir / "scenario.json").write_text(json.dumps({"scenario_id": "s-1", "environment": "isaac_sim", "task": "reach", "seed": 3, "parameters": {}, "hazards": {}}))
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": "run-1", "backend": "isaac_sim"}))
    (run_dir / "result.json").write_text(json.dumps({"task_success": False, "environmental_failure": True, "failure_type": "collapse", "severity": "high", "terminal": True}))
    raw = camera_dir / "rgb_000000.npy"; np.save(raw, np.zeros((12, 16, 4), dtype=np.uint8))
    (run_dir / "trajectory.jsonl").write_text(json.dumps({"record_type": "initial_observation", "observation": {"simulation_time": 0, "sensor_refs": [str(raw)]}}) + "\n")
    payload = _comparison_payload(tmp_path)
    pair_path = runs / "paired" / "pair-1" / "comparison.json"; pair_path.parent.mkdir(parents=True)
    pair_path.write_text(json.dumps(payload), encoding="utf-8")

    store = ExperimentStore(tmp_path / "index.sqlite3")
    counts = reindex_runs(store, runs)

    assert counts["pairs"] == 1
    artifacts = store.artifacts_for("experiment", "run-1")
    assert any(item["kind"] == "video" for item in artifacts)
    assert store.get_pair("pair-1") is not None


def test_media_export_and_reactor_manifest_preserve_authority_boundary(tmp_path: Path):
    run_dir = tmp_path / "runs" / "isaac" / "run-1"
    camera_dir = run_dir.parent / "camera" / "capture"
    run_dir.mkdir(parents=True)
    camera_dir.mkdir(parents=True)
    np.save(camera_dir / "invalid.npy", np.zeros((4,), dtype=np.uint8))
    np.save(camera_dir / "rgb.npy", np.zeros((12, 16, 4), dtype=np.uint8))
    (run_dir / "trajectory.jsonl").write_text(
        json.dumps({"record_type": "initial_observation", "observation": {"sensor_refs": [str(camera_dir / "invalid.npy"), str(camera_dir / "rgb.npy")]}}) + "\n"
    )
    replay = export_isaac_replay(run_dir)
    assert Path(replay["video_path"]).is_file()
    assert [Path(path).name for path in replay["preview_frame_paths"]] == ["frame_0000.png"]

    reactor_dir = tmp_path / "reactor"
    frames = reactor_dir / "frames"
    frames.mkdir(parents=True)
    frame = frames / "chunk-0001.png"
    Image.new("RGB", (16, 12), "black").save(frame)
    (reactor_dir / "summary.json").write_text(json.dumps({"chunks": [{"index": 1, "elapsed_ms": 42}]}))
    manifest = normalize_reactor_media(reactor_dir, [frame])
    assert Path(manifest["derived_video_path"]).is_file()
    assert manifest["media_sequence"] == [{"position": 0, "path": str(frame)}]
    assert manifest["chunk_metadata"] == [{"index": 1, "elapsed_ms": 42}]
    assert "synchronized" in manifest["timing_note"]
