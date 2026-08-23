"""Bounded, structured experiment memory for scenario selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness.schemas import ExperimentRecord


@dataclass(frozen=True, slots=True)
class ExperimentSummary:
    """A compact record that intentionally excludes raw trajectory content."""

    run_id: str
    scenario_id: str
    environment: str
    task: str
    backend: str
    task_success: bool
    environmental_failure: bool
    failure_type: str | None
    severity: str
    metrics: dict[str, Any]
    trajectory_ref: str

    @classmethod
    def from_record(cls, record: ExperimentRecord) -> "ExperimentSummary":
        evaluation = record.evaluation
        return cls(
            run_id=record.run_id,
            scenario_id=record.scenario.scenario_id,
            environment=record.scenario.environment,
            task=record.scenario.task,
            backend=record.backend,
            task_success=evaluation.task_success,
            environmental_failure=evaluation.environmental_failure,
            failure_type=evaluation.failure_type,
            severity=evaluation.severity.value,
            metrics=dict(evaluation.metrics),
            trajectory_ref=record.trajectory_ref,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "environment": self.environment,
            "task": self.task,
            "backend": self.backend,
            "task_success": self.task_success,
            "environmental_failure": self.environmental_failure,
            "failure_type": self.failure_type,
            "severity": self.severity,
            "metrics": dict(self.metrics),
            "trajectory_ref": self.trajectory_ref,
        }


class ExperimentMemory:
    """Keeps only the newest ``capacity`` structured summaries."""

    def __init__(self, capacity: int = 100) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least one")
        self.capacity = capacity
        self._records: list[ExperimentSummary] = []

    def add(self, record: ExperimentRecord) -> None:
        self._records.append(ExperimentSummary.from_record(record))
        overflow = len(self._records) - self.capacity
        if overflow > 0:
            del self._records[:overflow]

    def summaries(self) -> tuple[ExperimentSummary, ...]:
        return tuple(self._records)

    def __len__(self) -> int:
        return len(self._records)
