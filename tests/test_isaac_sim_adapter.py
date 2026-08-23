from dataclasses import replace

import pytest

from harness.environments.isaac_sim import (
    IsaacRuntimeState,
    IsaacScenarioConfig,
    IsaacSimEnvironment,
)
from harness.schemas import Action, Scenario


class FakeIsaacRuntime:
    """Local stand-in proving adapter behavior without Isaac Sim installed."""

    def __init__(self) -> None:
        self.config: IsaacScenarioConfig | None = None
        self.state = IsaacRuntimeState(
            simulation_time=0.0,
            robot_position=(0.0, 0.0, 0.25),
            robot_linear_velocity=(0.0, 0.0, 0.0),
            support_released=False,
        )
        self.released = False
        self.closed = False

    def reset(self, config: IsaacScenarioConfig) -> IsaacRuntimeState:
        self.config = config
        self.state = replace(
            self.state,
            simulation_time=0.0,
            robot_position=config.robot_start,
            robot_linear_velocity=(0.0, 0.0, 0.0),
            support_released=False,
        )
        self.released = False
        return self.state

    def set_planar_velocity(self, x_velocity: float, y_velocity: float) -> None:
        self.state = replace(self.state, robot_linear_velocity=(x_velocity, y_velocity, 0.0))

    def release_support(self) -> None:
        self.released = True
        self.state = replace(self.state, support_released=True)

    def advance(self, physics_steps: int) -> IsaacRuntimeState:
        x, y, z = self.state.robot_position
        x_velocity, y_velocity, _ = self.state.robot_linear_velocity
        self.state = replace(
            self.state,
            simulation_time=self.state.simulation_time + physics_steps / 60.0,
            robot_position=(x + x_velocity, y + y_velocity, z),
            sensor_refs=(f"/tmp/rgb-{physics_steps}.npy",),
        )
        return self.state

    def observe(self) -> IsaacRuntimeState:
        return self.state

    def close(self) -> None:
        self.closed = True


def test_isaac_adapter_translates_action_and_records_collapse_event():
    runtime = FakeIsaacRuntime()
    environment = IsaacSimEnvironment(runtime)
    observation = environment.reset(
        Scenario(
            environment="isaac_sim",
            task="reach_target",
            parameters={"target_position": [1.0, 0.0], "physics_steps_per_action": 12},
            hazards={"collapse_after_actions": 1},
        )
    )

    assert observation.state["task_complete"] is False
    result = environment.step(Action("set_planar_velocity", {"x": 1.0, "y": 0.0}))

    assert runtime.released is True
    assert result.done is True
    assert result.events[0].event_type == "structural_collapse"
    assert result.events[0].catastrophic is False
    assert result.observation.state["task_complete"] is True
    assert result.observation.sensor_refs == ("/tmp/rgb-12.npy",)
    assert result.observation.state["seed"] == 0


def test_isaac_adapter_validates_backend_schema_and_action_vocabulary():
    environment = IsaacSimEnvironment(FakeIsaacRuntime())
    with pytest.raises(ValueError, match="scenario.environment"):
        environment.reset(Scenario(environment="mock", task="reach"))
    with pytest.raises(ValueError, match="unsupported scenario parameters"):
        environment.reset(
            Scenario(environment="isaac_sim", task="reach", parameters={"arbitrary_code": "no"})
        )

    environment.reset(Scenario(environment="isaac_sim", task="reach"))
    with pytest.raises(ValueError, match="set_planar_velocity"):
        environment.step(Action("move", {"distance": 1.0}))


def test_isaac_adapter_closes_its_runtime_and_rejects_further_use():
    runtime = FakeIsaacRuntime()
    environment = IsaacSimEnvironment(runtime)
    environment.close()

    assert runtime.closed is True
    with pytest.raises(RuntimeError, match="closed"):
        environment.reset(Scenario(environment="isaac_sim", task="reach"))
