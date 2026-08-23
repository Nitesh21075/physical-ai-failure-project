"""Isaac Sim environment adapter with no Isaac dependency at import time.

The concrete ``IsaacSim50Runtime`` is created only when this module is used in
an Isaac Sim 5.x Python process.  The adapter itself is deliberately ordinary
Python so its scenario/action translation can be tested locally.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from harness.environments.base import Environment
from harness.schemas import Action, Event, Observation, Scenario, Severity, StepResult


class IsaacSimUnavailableError(RuntimeError):
    """Raised when the adapter is constructed outside an Isaac Sim runtime."""


@dataclass(frozen=True, slots=True)
class IsaacScenarioConfig:
    """The small, allow-listed configuration for the Phase 2 reference scene."""

    scenario_id: str
    target_position: tuple[float, float]
    robot_start: tuple[float, float, float]
    seed: int
    physics_steps_per_action: int
    collapse_after_actions: int | None
    terminal_on_collapse: bool


@dataclass(frozen=True, slots=True)
class IsaacRuntimeState:
    """Portable state sampled from the concrete simulator runtime."""

    simulation_time: float
    robot_position: tuple[float, float, float]
    robot_linear_velocity: tuple[float, float, float]
    support_released: bool
    sensor_refs: tuple[str, ...] = ()


class IsaacRuntime(Protocol):
    """Version-specific simulator operations hidden behind the stable adapter."""

    def reset(self, config: IsaacScenarioConfig) -> IsaacRuntimeState: ...

    def set_planar_velocity(self, x_velocity: float, y_velocity: float) -> None: ...

    def release_support(self) -> None: ...

    def advance(self, physics_steps: int) -> IsaacRuntimeState: ...

    def observe(self) -> IsaacRuntimeState: ...

    def close(self) -> None: ...


class IsaacSimEnvironment(Environment):
    """Phase 2 environment with a mobile rigid-body robot proxy and falling beam.

    Supported scenario parameters are ``target_position`` (``[x, y]``),
    ``robot_start`` (``[x, y, z]``), and ``physics_steps_per_action``.  The
    supported hazard is ``collapse_after_actions`` with optional
    ``terminal_on_collapse``.  The sole v0 action is ``set_planar_velocity``
    with numeric ``x`` and ``y`` values.
    """

    _PARAMETERS = {"target_position", "robot_start", "physics_steps_per_action"}
    _HAZARDS = {"collapse_after_actions", "terminal_on_collapse"}

    def __init__(self, runtime: IsaacRuntime | None = None) -> None:
        self._runtime = runtime if runtime is not None else IsaacSim50Runtime()
        self._config: IsaacScenarioConfig | None = None
        self._action_count = 0
        self._closed = False

    @property
    def backend_name(self) -> str:
        return "isaac_sim"

    def reset(self, scenario: Scenario) -> Observation:
        self._require_open()
        self._config = self._parse_scenario(scenario)
        self._action_count = 0
        return self._to_observation(self._runtime.reset(self._config))

    def step(self, action: Action) -> StepResult:
        self._require_reset()
        if action.name != "set_planar_velocity":
            raise ValueError("Isaac Sim v0 supports only 'set_planar_velocity' actions")
        x_velocity = self._number(action.parameters.get("x"), "action parameter 'x'")
        y_velocity = self._number(action.parameters.get("y"), "action parameter 'y'")

        self._runtime.set_planar_velocity(x_velocity, y_velocity)
        self._action_count += 1
        events: list[Event] = []
        assert self._config is not None
        if (
            self._config.collapse_after_actions is not None
            and not self._runtime.observe().support_released
            and self._action_count >= self._config.collapse_after_actions
        ):
            self._runtime.release_support()
            events.append(
                Event(
                    event_type="structural_collapse",
                    category="environmental",
                    severity=Severity.HIGH,
                    catastrophic=self._config.terminal_on_collapse,
                    details={"triggering_action": self._action_count},
                )
            )

        state = self._runtime.advance(self._config.physics_steps_per_action)
        observation = self._to_observation(state)
        done = bool(observation.state["task_complete"]) or (
            state.support_released and self._config.terminal_on_collapse
        )
        return StepResult(
            simulation_time=state.simulation_time,
            observation=observation,
            done=done,
            events=tuple(events),
            world_state=dict(observation.state),
        )

    def observe(self) -> Observation:
        self._require_reset()
        return self._to_observation(self._runtime.observe())

    def close(self) -> None:
        if not self._closed:
            self._runtime.close()
            self._closed = True

    def _to_observation(self, state: IsaacRuntimeState) -> Observation:
        assert self._config is not None
        target_x, target_y = self._config.target_position
        robot_x, robot_y, _ = state.robot_position
        task_complete = (robot_x - target_x) ** 2 + (robot_y - target_y) ** 2 <= 0.25**2
        return Observation(
            simulation_time=state.simulation_time,
            state={
                "robot_position": list(state.robot_position),
                "robot_linear_velocity": list(state.robot_linear_velocity),
                "target_position": [target_x, target_y],
                "seed": self._config.seed,
                "support_released": state.support_released,
                "action_count": self._action_count,
                "task_complete": task_complete,
            },
            sensor_refs=state.sensor_refs,
        )

    def _parse_scenario(self, scenario: Scenario) -> IsaacScenarioConfig:
        if scenario.environment != self.backend_name:
            raise ValueError("IsaacSimEnvironment requires scenario.environment == 'isaac_sim'")
        self._reject_unknown_keys(scenario.parameters, self._PARAMETERS, "scenario parameters")
        self._reject_unknown_keys(scenario.hazards, self._HAZARDS, "scenario hazards")
        target_position = self._vector(scenario.parameters.get("target_position", (2.0, 0.0)), 2)
        robot_start = self._vector(scenario.parameters.get("robot_start", (0.0, 0.0, 0.25)), 3)
        physics_steps = scenario.parameters.get("physics_steps_per_action", 12)
        if (
            isinstance(physics_steps, bool)
            or not isinstance(physics_steps, int)
            or physics_steps < 1
        ):
            raise ValueError("physics_steps_per_action must be a positive integer")
        collapse_after = scenario.hazards.get("collapse_after_actions")
        if collapse_after is not None and (
            isinstance(collapse_after, bool)
            or not isinstance(collapse_after, int)
            or collapse_after < 1
        ):
            raise ValueError("collapse_after_actions must be a positive integer")
        return IsaacScenarioConfig(
            scenario_id=scenario.scenario_id,
            target_position=(target_position[0], target_position[1]),
            robot_start=(robot_start[0], robot_start[1], robot_start[2]),
            seed=scenario.seed,
            physics_steps_per_action=physics_steps,
            collapse_after_actions=collapse_after,
            terminal_on_collapse=bool(scenario.hazards.get("terminal_on_collapse", False)),
        )

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("environment is closed")

    def _require_reset(self) -> None:
        self._require_open()
        if self._config is None:
            raise RuntimeError("reset must be called before observe or step")

    @staticmethod
    def _reject_unknown_keys(values: Any, allowed: set[str], description: str) -> None:
        unknown = set(values).difference(allowed)
        if unknown:
            raise ValueError(f"unsupported {description}: {', '.join(sorted(unknown))}")

    @classmethod
    def _vector(cls, value: Any, dimensions: int) -> tuple[float, ...]:
        if not isinstance(value, (list, tuple)) or len(value) != dimensions:
            raise ValueError(f"expected a numeric vector with {dimensions} values")
        return tuple(cls._number(item, "vector value") for item in value)

    @staticmethod
    def _number(value: Any, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be numeric")
        return float(value)


class IsaacSim50Runtime:
    """Isaac Sim 5.x standalone runtime for the bounded Phase 2 reference scene.

    This class intentionally imports Isaac Sim only after ``SimulationApp`` is
    launched.  It is not imported by package initializers or local test runs.
    """

    def __init__(self, sensor_output_dir: str | Path | None = None) -> None:
        try:
            import numpy as np
            from isaacsim import SimulationApp
        except ImportError as error:
            raise IsaacSimUnavailableError(
                "Isaac Sim 5.x is required. Run with the AWS container's python.sh."
            ) from error

        self._np = np
        self._app = SimulationApp({"headless": True})
        try:
            import omni.usd
            from isaacsim.core.api import World
            from isaacsim.core.api.objects import DynamicCuboid
            from isaacsim.sensors.camera import Camera
            from pxr import UsdPhysics
        except ImportError as error:
            self._app.close()
            raise IsaacSimUnavailableError(
                "The installed Isaac Sim runtime lacks the required 5.x core/camera APIs."
            ) from error

        self._omni_usd = omni.usd
        self._world_type = World
        self._dynamic_cuboid = DynamicCuboid
        self._camera_type = Camera
        self._usd_physics = UsdPhysics
        self._sensor_output_dir = Path(sensor_output_dir) if sensor_output_dir else None
        self._active_sensor_output_dir: Path | None = None
        self._world: Any = None
        self._robot: Any = None
        self._camera: Any = None
        self._beam_kinematic_attribute: Any = None
        self._support_released = False
        self._simulation_time = 0.0
        self._frame_index = 0

    def reset(self, config: IsaacScenarioConfig) -> IsaacRuntimeState:
        self._np.random.seed(config.seed)
        if self._sensor_output_dir is not None:
            scenario_key = sha256(config.scenario_id.encode("utf-8")).hexdigest()
            self._active_sensor_output_dir = self._sensor_output_dir / scenario_key
        self._omni_usd.get_context().new_stage()
        self._world = self._world_type(stage_units_in_meters=1.0)
        self._world.scene.add_default_ground_plane()
        np = self._np
        self._robot = self._world.scene.add(
            self._dynamic_cuboid(
                prim_path="/World/RobotProxy",
                name="robot_proxy",
                position=np.array(config.robot_start),
                scale=np.array([0.35, 0.35, 0.35]),
                color=np.array([0.1, 0.4, 0.9]),
                mass=5.0,
            )
        )
        self._world.scene.add(
            self._dynamic_cuboid(
                prim_path="/World/SupportBeam",
                name="support_beam",
                position=np.array([config.target_position[0], config.target_position[1], 2.5]),
                scale=np.array([1.5, 0.2, 0.2]),
                color=np.array([0.65, 0.35, 0.1]),
                mass=20.0,
            )
        )
        self._camera = self._camera_type(
            prim_path="/World/OverheadCamera",
            position=np.array([0.0, -6.0, 6.0]),
            resolution=(256, 256),
            frequency=60,
        )
        self._set_beam_kinematic(True)
        self._world.reset()
        self._camera.initialize()
        self._support_released = False
        self._simulation_time = 0.0
        self._frame_index = 0
        self._world.step(render=True)
        return self.observe()

    def set_planar_velocity(self, x_velocity: float, y_velocity: float) -> None:
        self._require_world()
        self._robot.set_linear_velocity(self._np.array([x_velocity, y_velocity, 0.0]))

    def release_support(self) -> None:
        self._require_world()
        self._set_beam_kinematic(False)
        self._support_released = True

    def advance(self, physics_steps: int) -> IsaacRuntimeState:
        self._require_world()
        for _ in range(physics_steps):
            self._world.step(render=True)
        self._simulation_time += physics_steps / 60.0
        return self.observe()

    def observe(self) -> IsaacRuntimeState:
        self._require_world()
        position, _ = self._robot.get_world_pose()
        velocity = self._robot.get_linear_velocity()
        sensor_refs = self._capture_camera()
        return IsaacRuntimeState(
            simulation_time=self._simulation_time,
            robot_position=tuple(float(value) for value in position),
            robot_linear_velocity=tuple(float(value) for value in velocity),
            support_released=self._support_released,
            sensor_refs=sensor_refs,
        )

    def close(self) -> None:
        self._app.close()

    def _set_beam_kinematic(self, enabled: bool) -> None:
        stage = self._omni_usd.get_context().get_stage()
        rigid_body = self._usd_physics.RigidBodyAPI.Get(stage, "/World/SupportBeam")
        attribute = rigid_body.GetKinematicEnabledAttr()
        if not attribute:
            attribute = rigid_body.CreateKinematicEnabledAttr()
        attribute.Set(enabled)
        self._beam_kinematic_attribute = attribute

    def _capture_camera(self) -> tuple[str, ...]:
        if self._active_sensor_output_dir is None:
            return ()
        self._active_sensor_output_dir.mkdir(parents=True, exist_ok=True)
        path = self._active_sensor_output_dir / f"rgb_{self._frame_index:06d}.npy"
        self._np.save(path, self._camera.get_rgba())
        self._frame_index += 1
        return (str(path),)

    def _require_world(self) -> None:
        if self._world is None:
            raise RuntimeError("reset must be called before using the Isaac runtime")
