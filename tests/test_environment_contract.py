import pytest

from harness.environments.mock import MockEnvironment
from harness.schemas import Action, Scenario


def test_mock_environment_obeys_reset_step_observe_contract():
    env = MockEnvironment()
    scenario = Scenario(
        environment="mock_warehouse",
        task="reach_target",
        parameters={"target_position": 2},
    )

    initial = env.reset(scenario)
    assert initial.state["position"] == 0
    first = env.step(Action("move", {"distance": 1}))
    assert first.done is False
    assert env.observe().state["position"] == 1
    second = env.step(Action("move", {"distance": 1}))
    assert second.done is True
    assert second.simulation_time == 2


def test_mock_environment_requires_reset_and_rejects_unknown_actions():
    env = MockEnvironment()
    with pytest.raises(RuntimeError, match="reset"):
        env.observe()

    env.reset(Scenario(environment="mock", task="reach"))
    with pytest.raises(ValueError, match="does not support"):
        env.step(Action("turn"))
