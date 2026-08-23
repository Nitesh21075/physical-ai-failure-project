from pathlib import Path

import pytest

from harness.environments.reactor import (
    ReactorConfigurationError,
    ReactorVideoChunk,
    ReactorVisualEnvironment,
)
from harness.schemas import Action, Scenario


class FakeReactorSession:
    def __init__(self) -> None:
        self.calls: list[object] = []
        self.chunks = [
            ReactorVideoChunk(0, ("runs/reactor/chunk-000.mp4",)),
            ReactorVideoChunk(1, ("runs/reactor/chunk-001.mp4",), generation_complete=True),
        ]
        self.closed = False

    def reset(self) -> None:
        self.calls.append("reset")

    def set_seed(self, seed: int) -> None:
        self.calls.append(("seed", seed))

    def upload_image(self, image_path: Path) -> str:
        self.calls.append(("upload", image_path))
        return "reactor://images/seed"

    def set_image(self, image_ref: str) -> None:
        self.calls.append(("image", image_ref))

    def set_prompt(self, prompt: str) -> None:
        self.calls.append(("prompt", prompt))

    def start(self) -> None:
        self.calls.append("start")

    def set_controls(self, controls: dict[str, object]) -> None:
        self.calls.append(("controls", controls))

    def wait_for_chunk(self, timeout_seconds: float) -> ReactorVideoChunk:
        self.calls.append(("wait", timeout_seconds))
        return self.chunks.pop(0)

    def close(self) -> None:
        self.closed = True


def scenario(seed_image: Path, **parameters: object) -> Scenario:
    return Scenario(
        environment="reactor/lingbot-world-2",
        task="visually navigate around the obstruction",
        seed=17,
        parameters={
            "prompt": "A mobile camera moves cautiously through a warehouse.",
            "seed_image_path": str(seed_image),
            **parameters,
        },
    )


def test_reactor_adapter_records_video_only_and_waits_for_chunk(tmp_path: Path):
    seed_image = tmp_path / "seed.png"
    seed_image.write_bytes(b"not decoded by the fake transport")
    session = FakeReactorSession()
    environment = ReactorVisualEnvironment(session)

    initial = environment.reset(scenario(seed_image, chunk_timeout_seconds=4))
    result = environment.step(
        Action(
            "set_camera_controls",
            {"move_longitudinal": "forward", "look_horizontal": "right", "rotation_speed_degrees": 12},
        )
    )

    assert initial.sensor_refs == ("runs/reactor/chunk-000.mp4",)
    assert initial.state == {
        "backend_kind": "generative_video",
        "model_name": "reactor/lingbot-world-2",
        "chunk_index": 0,
        "generation_complete": False,
    }
    assert result.world_state is None
    assert result.events == ()
    assert result.done is True
    assert result.observation.sensor_refs == ("runs/reactor/chunk-001.mp4",)
    assert session.calls == [
        "reset",
        ("seed", 17),
        ("upload", seed_image),
        ("image", "reactor://images/seed"),
        ("prompt", "A mobile camera moves cautiously through a warehouse."),
        "start",
        ("wait", 4.0),
        (
            "controls",
            {
                "move_longitudinal": "forward",
                "move_lateral": "idle",
                "look_horizontal": "right",
                "look_vertical": "idle",
                "rotation_speed_degrees": 12.0,
            },
        ),
        ("wait", 4.0),
    ]


def test_reactor_adapter_rejects_unsupported_claims_and_controls(tmp_path: Path):
    seed_image = tmp_path / "seed.png"
    seed_image.write_bytes(b"seed")
    environment = ReactorVisualEnvironment(FakeReactorSession())

    with pytest.raises(ReactorConfigurationError, match="scenario.environment"):
        environment.reset(Scenario(environment="mock", task="reach"))
    with pytest.raises(ReactorConfigurationError, match="physical hazards"):
        environment.reset(
            Scenario(
                environment="reactor/lingbot-world-2",
                task="visually navigate around the obstruction",
                parameters={
                    "prompt": "A mobile camera moves cautiously through a warehouse.",
                    "seed_image_path": str(seed_image),
                },
                hazards={"collapse": True},
            )
        )
    with pytest.raises(ReactorConfigurationError, match="unsupported scenario parameters"):
        environment.reset(scenario(seed_image, joint_positions=[1, 2]))

    environment.reset(scenario(seed_image))
    with pytest.raises(ReactorConfigurationError, match="set_camera_controls"):
        environment.step(Action("set_joint_positions", {}))
    with pytest.raises(ReactorConfigurationError, match="move_longitudinal"):
        environment.step(Action("set_camera_controls", {"move_longitudinal": "teleport"}))


def test_reactor_adapter_closes_session_and_rejects_further_use():
    session = FakeReactorSession()
    environment = ReactorVisualEnvironment(session)
    environment.close()

    assert session.closed is True
    with pytest.raises(RuntimeError, match="closed"):
        environment.observe()
