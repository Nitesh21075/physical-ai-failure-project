"""Small, serializable schemas shared by every harness backend.

These models deliberately describe the boundary between orchestration and an
environment.  A backend may keep richer native state internally, but it should
emit these portable records for experiments and comparison work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping
from uuid import uuid4


class SchemaValidationError(ValueError):
    """Raised when data cannot represent a harness schema."""


class Severity(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _non_empty_string(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{field_name} must be a non-empty string")


def _mapping(value: Mapping[str, Any] | None, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise SchemaValidationError(f"{field_name} must be a mapping")
    return dict(value)


@dataclass(frozen=True, slots=True)
class Scenario:
    environment: str
    task: str
    seed: int = 0
    parameters: Mapping[str, Any] = field(default_factory=dict)
    hazards: Mapping[str, Any] = field(default_factory=dict)
    scenario_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        _non_empty_string(self.environment, "environment")
        _non_empty_string(self.task, "task")
        _non_empty_string(self.scenario_id, "scenario_id")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise SchemaValidationError("seed must be an integer")
        object.__setattr__(self, "parameters", _mapping(self.parameters, "parameters"))
        object.__setattr__(self, "hazards", _mapping(self.hazards, "hazards"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Scenario":
        return cls(
            scenario_id=value.get("scenario_id", str(uuid4())),
            environment=value["environment"],
            task=value["task"],
            seed=value.get("seed", 0),
            parameters=value.get("parameters", {}),
            hazards=value.get("hazards", {}),
        )


@dataclass(frozen=True, slots=True)
class Observation:
    simulation_time: float
    state: Mapping[str, Any] = field(default_factory=dict)
    sensor_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.simulation_time < 0:
            raise SchemaValidationError("simulation_time cannot be negative")
        object.__setattr__(self, "state", _mapping(self.state, "state"))
        object.__setattr__(self, "sensor_refs", tuple(self.sensor_refs))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Action:
    name: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _non_empty_string(self.name, "action name")
        object.__setattr__(self, "parameters", _mapping(self.parameters, "action parameters"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Event:
    event_type: str
    category: str
    severity: Severity = Severity.NONE
    catastrophic: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _non_empty_string(self.event_type, "event_type")
        _non_empty_string(self.category, "event category")
        if not isinstance(self.severity, Severity):
            object.__setattr__(self, "severity", Severity(self.severity))
        object.__setattr__(self, "details", _mapping(self.details, "event details"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StepResult:
    simulation_time: float
    observation: Observation
    done: bool
    events: tuple[Event, ...] = ()
    world_state: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.simulation_time < 0:
            raise SchemaValidationError("simulation_time cannot be negative")
        if not isinstance(self.observation, Observation):
            raise SchemaValidationError("observation must be an Observation")
        object.__setattr__(self, "events", tuple(self.events))
        if not all(isinstance(event, Event) for event in self.events):
            raise SchemaValidationError("events must contain Event values")
        if self.world_state is not None:
            object.__setattr__(self, "world_state", _mapping(self.world_state, "world_state"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TrajectoryStep:
    index: int
    observation: Observation
    action: Action
    result: StepResult

    def __post_init__(self) -> None:
        if self.index < 0:
            raise SchemaValidationError("trajectory step index cannot be negative")
        if not isinstance(self.observation, Observation):
            raise SchemaValidationError("trajectory observation must be an Observation")
        if not isinstance(self.action, Action):
            raise SchemaValidationError("trajectory action must be an Action")
        if not isinstance(self.result, StepResult):
            raise SchemaValidationError("trajectory result must be a StepResult")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    task_success: bool
    environmental_failure: bool
    failure_type: str | None
    severity: Severity
    robot_safety_events: tuple[Event, ...] = ()
    terminal: bool = False
    metrics: Mapping[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.severity, Severity):
            object.__setattr__(self, "severity", Severity(self.severity))
        if self.environmental_failure and not self.failure_type:
            raise SchemaValidationError("environmental failures require a failure_type")
        if not self.environmental_failure and self.failure_type is not None:
            raise SchemaValidationError("failure_type requires environmental_failure")
        object.__setattr__(self, "robot_safety_events", tuple(self.robot_safety_events))
        object.__setattr__(self, "metrics", _mapping(self.metrics, "metrics"))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    run_id: str
    scenario: Scenario
    backend: str
    trajectory_ref: str
    evaluation: EvaluationResult
    created_at: str

    def __post_init__(self) -> None:
        _non_empty_string(self.run_id, "run_id")
        _non_empty_string(self.backend, "backend")
        _non_empty_string(self.trajectory_ref, "trajectory_ref")
        _non_empty_string(self.created_at, "created_at")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
