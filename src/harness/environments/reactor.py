"""Reactor visual-world adapter.

This module deliberately stops at Reactor's documented boundary: a session
accepts visual steering commands and yields generated-video chunks.  It does
not infer robot pose, contacts, or physical failure events from pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from harness.environments.base import Environment
from harness.schemas import Action, Observation, Scenario, StepResult


class ReactorConfigurationError(ValueError):
    """Raised when a Scenario or Action is outside the visual adapter contract."""


@dataclass(frozen=True, slots=True)
class ReactorVisualConfig:
    """Validated conditioning inputs for one LingBot World 2 session."""

    prompt: str
    seed_image_path: Path
    seed: int
    chunk_timeout_seconds: float = 30.0
    model_name: str = "reactor/lingbot-world-2"


@dataclass(frozen=True, slots=True)
class ReactorVideoChunk:
    """A completed model-to-client video chunk saved by the transport."""

    index: int
    sensor_refs: tuple[str, ...]
    generation_complete: bool = False

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("chunk index cannot be negative")
        object.__setattr__(self, "sensor_refs", tuple(self.sensor_refs))


class ReactorSession(Protocol):
    """Small, testable transport boundary around a Reactor session.

    A production implementation may use Reactor's SDK/WebRTC connection, but
    must persist received frames/chunks and return their stable artifact refs.
    """

    def reset(self) -> None: ...

    def set_seed(self, seed: int) -> None: ...

    def upload_image(self, image_path: Path) -> str: ...

    def set_image(self, image_ref: str) -> None: ...

    def set_prompt(self, prompt: str) -> None: ...

    def start(self) -> None: ...

    def set_controls(self, controls: Mapping[str, Any]) -> None: ...

    def wait_for_chunk(self, timeout_seconds: float) -> ReactorVideoChunk: ...

    def close(self) -> None: ...


class ReactorVisualEnvironment(Environment):
    """Synchronous wrapper around asynchronous Reactor video chunks.

    ``Observation.state`` contains session metadata only.  ``world_state`` and
    environmental events are intentionally absent because this backend has no
    authoritative physics or event stream.
    """

    _SCENARIO_PARAMETERS = {"prompt", "seed_image_path", "chunk_timeout_seconds", "model_name"}
    _CONTROL_VALUES = {
        "move_longitudinal": {"idle", "forward", "backward"},
        "move_lateral": {"idle", "strafe_left", "strafe_right"},
        "look_horizontal": {"idle", "left", "right"},
        "look_vertical": {"idle", "up", "down"},
    }
    _OPTIONAL_CONTROL_VALUES = {"rotation_speed_degrees"}

    def __init__(self, session: ReactorSession) -> None:
        self._session = session
        self._config: ReactorVisualConfig | None = None
        self._latest_chunk: ReactorVideoChunk | None = None
        self._closed = False

    @property
    def backend_name(self) -> str:
        return self._config.model_name if self._config is not None else "reactor/lingbot-world-2"

    def reset(self, scenario: Scenario) -> Observation:
        self._ensure_open()
        if scenario.environment != self.backend_name:
            raise ReactorConfigurationError(
                f"scenario.environment must be {self.backend_name!r}, got {scenario.environment!r}"
            )
        config = self._scenario_config(scenario)
        self._session.reset()
        self._session.set_seed(config.seed)
        image_ref = self._session.upload_image(config.seed_image_path)
        self._session.set_image(image_ref)
        self._session.set_prompt(config.prompt)
        self._session.start()
        self._config = config
        self._latest_chunk = self._session.wait_for_chunk(config.chunk_timeout_seconds)
        return self._observation(self._latest_chunk)

    def step(self, action: Action) -> StepResult:
        self._ensure_ready()
        controls = self._controls(action)
        self._session.set_controls(controls)
        assert self._config is not None
        chunk = self._session.wait_for_chunk(self._config.chunk_timeout_seconds)
        self._latest_chunk = chunk
        return StepResult(
            simulation_time=float(chunk.index),
            observation=self._observation(chunk),
            done=chunk.generation_complete,
        )

    def observe(self) -> Observation:
        self._ensure_ready()
        assert self._latest_chunk is not None
        return self._observation(self._latest_chunk)

    def close(self) -> None:
        if not self._closed:
            self._session.close()
            self._closed = True

    def _scenario_config(self, scenario: Scenario) -> ReactorVisualConfig:
        unsupported = set(scenario.parameters) - self._SCENARIO_PARAMETERS
        if unsupported:
            raise ReactorConfigurationError(f"unsupported scenario parameters: {sorted(unsupported)}")
        if scenario.hazards:
            raise ReactorConfigurationError("Reactor visual sessions do not accept physical hazards")
        prompt = scenario.parameters.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ReactorConfigurationError("parameters.prompt must be a non-empty string")
        image_value = scenario.parameters.get("seed_image_path")
        if not isinstance(image_value, str) or not image_value.strip():
            raise ReactorConfigurationError("parameters.seed_image_path must be a non-empty path")
        image_path = Path(image_value)
        if not image_path.is_file():
            raise ReactorConfigurationError(f"seed image does not exist: {image_path}")
        timeout = scenario.parameters.get("chunk_timeout_seconds", 30.0)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ReactorConfigurationError("parameters.chunk_timeout_seconds must be positive")
        model_name = scenario.parameters.get("model_name", "reactor/lingbot-world-2")
        if model_name != "reactor/lingbot-world-2":
            raise ReactorConfigurationError("only reactor/lingbot-world-2 is supported")
        return ReactorVisualConfig(prompt, image_path, scenario.seed, float(timeout), model_name)

    def _controls(self, action: Action) -> dict[str, Any]:
        if action.name != "set_camera_controls":
            raise ReactorConfigurationError("Reactor only supports set_camera_controls actions")
        unsupported = set(action.parameters) - set(self._CONTROL_VALUES) - self._OPTIONAL_CONTROL_VALUES
        if unsupported:
            raise ReactorConfigurationError(f"unsupported camera controls: {sorted(unsupported)}")
        controls: dict[str, Any] = {}
        for name, allowed_values in self._CONTROL_VALUES.items():
            value = action.parameters.get(name, "idle")
            if value not in allowed_values:
                raise ReactorConfigurationError(f"{name} must be one of {sorted(allowed_values)}")
            controls[name] = value
        speed = action.parameters.get("rotation_speed_degrees")
        if speed is not None:
            if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not 0 <= speed <= 30:
                raise ReactorConfigurationError("rotation_speed_degrees must be between 0 and 30")
            controls["rotation_speed_degrees"] = float(speed)
        return controls

    def _observation(self, chunk: ReactorVideoChunk) -> Observation:
        assert self._config is not None
        return Observation(
            simulation_time=float(chunk.index),
            sensor_refs=chunk.sensor_refs,
            state={
                "backend_kind": "generative_video",
                "model_name": self._config.model_name,
                "chunk_index": chunk.index,
                "generation_complete": chunk.generation_complete,
            },
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Reactor environment is closed")

    def _ensure_ready(self) -> None:
        self._ensure_open()
        if self._config is None or self._latest_chunk is None:
            raise RuntimeError("Reactor environment must be reset before use")
