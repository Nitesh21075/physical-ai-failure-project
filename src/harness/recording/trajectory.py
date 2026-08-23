"""Filesystem recorder for small, inspectable JSON experiment artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.schemas import (
    Action,
    EvaluationResult,
    Observation,
    Scenario,
    StepResult,
    TrajectoryStep,
)


@dataclass(frozen=True, slots=True)
class RecordedArtifacts:
    run_directory: Path
    trajectory_path: Path
    result_path: Path


class TrajectoryRecorder:
    """Writes one run per directory without embedding large media in JSON."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def start_run(self, run_id: str, scenario: Scenario, backend: str) -> "TrajectorySession":
        run_directory = self.root / run_id
        if run_directory.exists():
            raise FileExistsError(f"run already exists: {run_directory}")
        run_directory.mkdir(parents=True)
        self._write_json(run_directory / "scenario.json", scenario.to_dict())
        self._write_json(run_directory / "metadata.json", {"run_id": run_id, "backend": backend})
        return TrajectorySession(run_directory, run_directory / "trajectory.jsonl")

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class TrajectorySession:
    def __init__(self, run_directory: Path, trajectory_path: Path) -> None:
        self.run_directory = run_directory
        self.trajectory_path = trajectory_path
        self._finished = False

    def record_initial_observation(self, observation: Observation) -> None:
        self._append({"record_type": "initial_observation", "observation": observation.to_dict()})

    def record_step(self, step: TrajectoryStep) -> None:
        self._append(
            {
                "record_type": "step",
                "index": step.index,
                "observation": step.observation.to_dict(),
                "action": step.action.to_dict(),
                "result": step.result.to_dict(),
            }
        )

    def finish(self, evaluation: EvaluationResult) -> RecordedArtifacts:
        if self._finished:
            raise RuntimeError("trajectory session is already finished")
        result_path = self.run_directory / "result.json"
        result_path.write_text(
            json.dumps(evaluation.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self._finished = True
        return RecordedArtifacts(self.run_directory, self.trajectory_path, result_path)

    def _append(self, value: dict[str, Any]) -> None:
        if self._finished:
            raise RuntimeError("trajectory session is already finished")
        with self.trajectory_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(value, sort_keys=True) + "\n")
