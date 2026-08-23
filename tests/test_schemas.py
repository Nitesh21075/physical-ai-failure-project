import pytest

from harness.schemas import EvaluationResult, Scenario, SchemaValidationError, Severity


def test_scenario_round_trips_to_json_compatible_dict():
    scenario = Scenario(
        scenario_id="scenario-1",
        environment="mock_warehouse",
        task="reach_target",
        seed=42,
        parameters={"target_position": 2},
        hazards={"collapse_after_moves": 1},
    )

    assert Scenario.from_dict(scenario.to_dict()) == scenario


def test_evaluation_disallows_an_unclassified_environmental_failure():
    with pytest.raises(SchemaValidationError, match="failure_type"):
        EvaluationResult(
            task_success=True,
            environmental_failure=True,
            failure_type=None,
            severity=Severity.HIGH,
        )
