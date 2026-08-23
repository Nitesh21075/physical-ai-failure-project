"""Simple deterministic components for local end-to-end experiments."""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence
from uuid import uuid4

from harness.memory import ExperimentSummary
from harness.schemas import Action, Observation, Scenario


class StaticScenarioAgent:
    """Returns a copy of one scenario, assigning a fresh ID for each run."""

    def __init__(self, scenario: Scenario) -> None:
        self._scenario = scenario
        self.seen_memory: tuple[ExperimentSummary, ...] = ()

    def propose(self, memory: Sequence[ExperimentSummary]) -> Scenario:
        self.seen_memory = tuple(memory)
        return replace(self._scenario, scenario_id=str(uuid4()))


class MockRobotController:
    """Moves straight toward the mock environment's declared target."""

    def __init__(self, step_size: float = 1.0) -> None:
        if step_size <= 0:
            raise ValueError("step_size must be positive")
        self.step_size = step_size

    def act(self, observation: Observation) -> Action:
        position = float(observation.state["position"])
        target = float(observation.state["target_position"])
        return Action(name="move", parameters={"distance": min(self.step_size, target - position)})
