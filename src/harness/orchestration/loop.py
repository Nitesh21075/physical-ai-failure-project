"""The backend-independent closed-loop Plan-B experiment orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, Sequence
from uuid import uuid4

from harness.environments.base import Environment
from harness.memory import ExperimentMemory, ExperimentSummary
from harness.recording.trajectory import TrajectoryRecorder
from harness.schemas import (
    Action,
    EvaluationResult,
    ExperimentRecord,
    Observation,
    Scenario,
    TrajectoryStep,
)


class ScenarioAgent(Protocol):
    def propose(self, memory: Sequence[ExperimentSummary]) -> Scenario: ...


class RobotController(Protocol):
    def act(self, observation: Observation) -> Action: ...


class Evaluator(Protocol):
    def evaluate(
        self,
        scenario: Scenario,
        initial_observation: Observation,
        trajectory: Sequence[TrajectoryStep],
    ) -> EvaluationResult: ...


class RunLimitExceeded(RuntimeError):
    """Raised when an environment does not terminate within the configured bound."""


class Orchestrator:
    """Run one deterministic closed-loop experiment against any Environment."""

    def __init__(
        self,
        environment: Environment,
        scenario_agent: ScenarioAgent,
        robot_controller: RobotController,
        evaluator: Evaluator,
        recorder: TrajectoryRecorder,
        memory: ExperimentMemory | None = None,
        max_steps: int = 1_000,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least one")
        self.environment = environment
        self.scenario_agent = scenario_agent
        self.robot_controller = robot_controller
        self.evaluator = evaluator
        self.recorder = recorder
        self.memory = memory if memory is not None else ExperimentMemory()
        self.max_steps = max_steps

    def run_one(self) -> ExperimentRecord:
        scenario = self.scenario_agent.propose(self.memory.summaries())
        if not isinstance(scenario, Scenario):
            raise TypeError("scenario agent must return a Scenario")

        run_id = str(uuid4())
        initial_observation = self.environment.reset(scenario)
        session = self.recorder.start_run(run_id, scenario, self.environment.backend_name)
        session.record_initial_observation(initial_observation)
        observation = initial_observation
        trajectory: list[TrajectoryStep] = []

        for index in range(self.max_steps):
            action = self.robot_controller.act(observation)
            if not isinstance(action, Action):
                raise TypeError("robot controller must return an Action")
            result = self.environment.step(action)
            step = TrajectoryStep(index=index, observation=observation, action=action, result=result)
            trajectory.append(step)
            session.record_step(step)
            if result.done:
                break
            observation = result.observation
        else:
            raise RunLimitExceeded(f"experiment {run_id} did not finish within {self.max_steps} steps")

        evaluation = self.evaluator.evaluate(scenario, initial_observation, tuple(trajectory))
        artifacts = session.finish(evaluation)
        record = ExperimentRecord(
            run_id=run_id,
            scenario=scenario,
            backend=self.environment.backend_name,
            trajectory_ref=str(artifacts.trajectory_path),
            evaluation=evaluation,
            created_at=datetime.now(UTC).isoformat(),
        )
        self.memory.add(record)
        return record
