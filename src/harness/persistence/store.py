"""SQLite metadata index for recorded harness experiments.

The database deliberately contains paths and compact metadata only.  Run
directories, trajectories, NumPy frames, videos, and native Reactor metadata
remain the source of truth and can recreate this index with ``reindex_runs``.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import closing
from enum import StrEnum
from pathlib import Path
from typing import Any

from harness.schemas import ExperimentRecord


class ReviewState(StrEnum):
    UNREVIEWED = "unreviewed"
    VALID_DISCREPANCY = "valid_discrepancy"
    BAD_WORLD_MODEL_GENERATION = "bad_world_model_generation"
    BAD_SCENARIO = "bad_scenario"
    SIMULATOR_ARTIFACT = "simulator_artifact"
    INCONCLUSIVE = "inconclusive"


class ExperimentStore:
    """A replaceable SQLite index, intentionally independent of execution."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    run_id TEXT PRIMARY KEY,
                    backend TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    task TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    created_at TEXT,
                    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    task_success INTEGER,
                    environmental_failure INTEGER,
                    failure_type TEXT,
                    severity TEXT,
                    terminal INTEGER,
                    trajectory_path TEXT,
                    run_directory TEXT,
                    scenario_json TEXT NOT NULL,
                    result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS paired_experiments (
                    pair_id TEXT PRIMARY KEY,
                    isaac_run_id TEXT NOT NULL,
                    reactor_run_id TEXT NOT NULL,
                    task TEXT NOT NULL,
                    scenario_id TEXT,
                    seed INTEGER NOT NULL,
                    comparison_status TEXT NOT NULL,
                    action_alignment TEXT NOT NULL,
                    alignment_note TEXT NOT NULL,
                    comparison_reason TEXT NOT NULL,
                    visual_event_type TEXT,
                    visual_observed INTEGER,
                    visual_confidence REAL,
                    visual_assessor TEXT,
                    comparison_path TEXT NOT NULL,
                    created_at TEXT,
                    review_state TEXT NOT NULL DEFAULT 'unreviewed',
                    FOREIGN KEY(isaac_run_id) REFERENCES experiments(run_id),
                    FOREIGN KEY(reactor_run_id) REFERENCES experiments(run_id)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_type TEXT NOT NULL CHECK(owner_type IN ('experiment', 'pair')),
                    owner_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(owner_type, owner_id, kind, path)
                );
                CREATE INDEX IF NOT EXISTS idx_experiments_created_at ON experiments(created_at);
                CREATE INDEX IF NOT EXISTS idx_pairs_status ON paired_experiments(comparison_status);
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(paired_experiments)")}
            if "created_at" not in columns:
                connection.execute("ALTER TABLE paired_experiments ADD COLUMN created_at TEXT")
            connection.commit()

    def upsert_experiment(
        self,
        record: ExperimentRecord | Mapping[str, Any],
        *,
        run_directory: str | Path | None = None,
        result_path: str | Path | None = None,
    ) -> None:
        payload = record.to_dict() if isinstance(record, ExperimentRecord) else dict(record)
        scenario = payload["scenario"]
        evaluation = payload["evaluation"]
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO experiments (
                    run_id, backend, scenario_id, task, seed, created_at, task_success,
                    environmental_failure, failure_type, severity, terminal, trajectory_path,
                    run_directory, scenario_json, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    backend=excluded.backend, scenario_id=excluded.scenario_id, task=excluded.task,
                    seed=excluded.seed, created_at=COALESCE(excluded.created_at, experiments.created_at),
                    task_success=excluded.task_success, environmental_failure=excluded.environmental_failure,
                    failure_type=excluded.failure_type, severity=excluded.severity,
                    terminal=excluded.terminal, trajectory_path=excluded.trajectory_path,
                    run_directory=COALESCE(excluded.run_directory, experiments.run_directory),
                    scenario_json=excluded.scenario_json, result_json=excluded.result_json,
                    indexed_at=CURRENT_TIMESTAMP
                """,
                (
                    payload["run_id"], payload["backend"], scenario["scenario_id"], scenario["task"],
                    scenario["seed"], payload.get("created_at"), int(evaluation["task_success"]),
                    int(evaluation["environmental_failure"]), evaluation.get("failure_type"),
                    evaluation["severity"], int(evaluation.get("terminal", False)),
                    str(payload["trajectory_ref"]), str(run_directory) if run_directory else None,
                    json.dumps(scenario, sort_keys=True), json.dumps(evaluation, sort_keys=True),
                ),
            )
            connection.commit()

    def register_artifact(
        self, owner_type: str, owner_id: str, kind: str, path: str | Path,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if owner_type not in {"experiment", "pair"}:
            raise ValueError("owner_type must be 'experiment' or 'pair'")
        with closing(self._connect()) as connection:
            connection.execute(
                """INSERT INTO artifacts(owner_type, owner_id, kind, path, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(owner_type, owner_id, kind, path) DO UPDATE SET
                metadata_json=excluded.metadata_json""",
                (owner_type, owner_id, kind, str(path), json.dumps(metadata or {}, sort_keys=True)),
            )
            connection.commit()

    def replace_artifacts(
        self, owner_type: str, owner_id: str, artifacts: Iterable[tuple[str, str | Path, Mapping[str, Any] | None]],
    ) -> None:
        unique: dict[tuple[str, str], Mapping[str, Any] | None] = {}
        for kind, path, metadata in artifacts:
            unique[(kind, str(path))] = metadata
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM artifacts WHERE owner_type = ? AND owner_id = ?", (owner_type, owner_id))
            connection.executemany(
                "INSERT INTO artifacts(owner_type, owner_id, kind, path, metadata_json) VALUES (?, ?, ?, ?, ?)",
                [(owner_type, owner_id, kind, path, json.dumps(metadata or {}, sort_keys=True)) for (kind, path), metadata in unique.items()],
            )
            connection.commit()

    def upsert_pair(
        self, payload: Mapping[str, Any], comparison_path: str | Path, *, created_at: str | None = None
    ) -> None:
        matched = payload["matched_experiment"]
        specification = matched["specification"]
        comparison = payload["comparison"]
        assessment = comparison.get("visual_assessment") or {}
        observed = assessment.get("observed")
        with closing(self._connect()) as connection:
            connection.execute(
                """INSERT INTO paired_experiments(
                    pair_id, isaac_run_id, reactor_run_id, task, scenario_id, seed,
                    comparison_status, action_alignment, alignment_note, comparison_reason,
                    visual_event_type, visual_observed, visual_confidence, visual_assessor,
                    comparison_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pair_id) DO UPDATE SET
                    isaac_run_id=excluded.isaac_run_id, reactor_run_id=excluded.reactor_run_id,
                    task=excluded.task, scenario_id=excluded.scenario_id, seed=excluded.seed,
                    comparison_status=excluded.comparison_status, action_alignment=excluded.action_alignment,
                    alignment_note=excluded.alignment_note, comparison_reason=excluded.comparison_reason,
                    visual_event_type=excluded.visual_event_type, visual_observed=excluded.visual_observed,
                    visual_confidence=excluded.visual_confidence, visual_assessor=excluded.visual_assessor,
                    comparison_path=excluded.comparison_path,
                    created_at=COALESCE(excluded.created_at, paired_experiments.created_at)""",
                (
                    specification["pair_id"], matched["isaac_record"]["run_id"],
                    matched["neural_record"]["run_id"], specification["task"],
                    specification["isaac_scenario"]["scenario_id"], specification["seed"],
                    comparison["status"], comparison["action_alignment"], specification["alignment_note"],
                    comparison["reason"], assessment.get("event_type"),
                    None if observed is None else int(observed), assessment.get("confidence"),
                    assessment.get("assessor"), str(comparison_path),
                    created_at,
                ),
            )
            connection.commit()

    def set_review_state(self, pair_id: str, state: ReviewState | str) -> None:
        state = ReviewState(state)
        with closing(self._connect()) as connection:
            result = connection.execute(
                "UPDATE paired_experiments SET review_state = ? WHERE pair_id = ?", (state.value, pair_id)
            )
            if result.rowcount != 1:
                raise KeyError(f"unknown paired experiment: {pair_id}")
            connection.commit()

    def list_experiments(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM experiments ORDER BY created_at DESC, run_id DESC").fetchall()
        return [self._experiment_row(row) for row in rows]

    def get_experiment(self, run_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM experiments WHERE run_id = ?", (run_id,)).fetchone()
        return self._experiment_row(row) if row else None

    def list_pairs(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM paired_experiments ORDER BY pair_id DESC").fetchall()
        return [self._pair_row(row) for row in rows]

    def get_pair(self, pair_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM paired_experiments WHERE pair_id = ?", (pair_id,)).fetchone()
        return self._pair_row(row) if row else None

    def artifacts_for(self, owner_type: str, owner_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE owner_type = ? AND owner_id = ? ORDER BY artifact_id",
                (owner_type, owner_id),
            ).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]

    @staticmethod
    def _experiment_row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["scenario"] = json.loads(result.pop("scenario_json"))
        result["evaluation"] = json.loads(result.pop("result_json")) if result["result_json"] else None
        for field in ("task_success", "environmental_failure", "terminal"):
            if result[field] is not None:
                result[field] = bool(result[field])
        return result

    @staticmethod
    def _pair_row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        if result["visual_observed"] is not None:
            result["visual_observed"] = bool(result["visual_observed"])
        return result
