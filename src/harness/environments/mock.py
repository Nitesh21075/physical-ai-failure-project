"""Deterministic environment used to develop the backend-neutral loop."""

from __future__ import annotations

from typing import Any

from harness.environments.base import Environment
from harness.schemas import Action, Event, Observation, Scenario, Severity, StepResult


class MockEnvironment(Environment):
    """A short reach task with an optional action-triggered structural collapse.

    ``collapse_after_moves`` models an environmental consequence independent of
    task completion.  Unless ``terminal_on_collapse`` is set, the robot can
    still reach its target after the collapse.  This makes the important Plan-B
    distinction observable in tests: task success need not mean a safe run.
    """

    def __init__(self) -> None:
        self._scenario: Scenario | None = None
        self._position = 0.0
        self._target_position = 1.0
        self._move_count = 0
        self._collapse_after_moves: int | None = None
        self._terminal_on_collapse = False
        self._collapsed = False
        self._closed = False

    @property
    def backend_name(self) -> str:
        return "mock"

    def reset(self, scenario: Scenario) -> Observation:
        if self._closed:
            raise RuntimeError("environment is closed")
        self._scenario = scenario
        self._position = 0.0
        self._move_count = 0
        self._collapsed = False
        self._target_position = self._positive_number(
            scenario.parameters.get("target_position", 2.0), "target_position"
        )
        self._collapse_after_moves = self._positive_optional_int(
            scenario.hazards.get("collapse_after_moves")
        )
        self._terminal_on_collapse = bool(scenario.hazards.get("terminal_on_collapse", False))
        return self.observe()

    def step(self, action: Action) -> StepResult:
        self._require_reset()
        if action.name != "move":
            raise ValueError(f"mock environment does not support action {action.name!r}")

        distance = self._positive_number(action.parameters.get("distance", 1.0), "distance")
        self._position += distance
        self._move_count += 1
        events: list[Event] = []
        if (
            not self._collapsed
            and self._collapse_after_moves is not None
            and self._move_count >= self._collapse_after_moves
        ):
            self._collapsed = True
            events.append(
                Event(
                    event_type="structural_collapse",
                    category="environmental",
                    severity=Severity.HIGH,
                    catastrophic=self._terminal_on_collapse,
                    details={"triggering_move": self._move_count},
                )
            )

        done = self._position >= self._target_position or (
            self._collapsed and self._terminal_on_collapse
        )
        observation = self.observe()
        return StepResult(
            simulation_time=float(self._move_count),
            observation=observation,
            done=done,
            events=tuple(events),
            world_state=dict(observation.state),
        )

    def observe(self) -> Observation:
        self._require_reset()
        return Observation(
            simulation_time=float(self._move_count),
            state={
                "position": self._position,
                "target_position": self._target_position,
                "move_count": self._move_count,
                "structural_collapsed": self._collapsed,
                "task_complete": self._position >= self._target_position,
            },
        )

    def close(self) -> None:
        self._closed = True

    def _require_reset(self) -> None:
        if self._closed:
            raise RuntimeError("environment is closed")
        if self._scenario is None:
            raise RuntimeError("reset must be called before observe or step")

    @staticmethod
    def _positive_number(value: Any, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"{name} must be a positive number")
        return float(value)

    @staticmethod
    def _positive_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("collapse_after_moves must be a positive integer")
        return value
