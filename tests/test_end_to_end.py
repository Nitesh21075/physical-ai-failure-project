import json
from pathlib import Path

from harness.agents.mock import MockRobotController, StaticScenarioAgent
from harness.environments.mock import MockEnvironment
from harness.evaluation.rule_based import RuleBasedEvaluator
from harness.memory import ExperimentMemory
from harness.orchestration.loop import Orchestrator
from harness.recording.trajectory import TrajectoryRecorder
from harness.schemas import Scenario, Severity


def test_mock_loop_records_task_success_and_environmental_failure(tmp_path: Path):
    scenario_agent = StaticScenarioAgent(
        Scenario(
            environment="mock_warehouse",
            task="reach_target",
            parameters={"target_position": 2},
            hazards={"collapse_after_moves": 1},
        )
    )
    memory = ExperimentMemory(capacity=2)
    orchestrator = Orchestrator(
        environment=MockEnvironment(),
        scenario_agent=scenario_agent,
        robot_controller=MockRobotController(),
        evaluator=RuleBasedEvaluator(),
        recorder=TrajectoryRecorder(tmp_path / "runs"),
        memory=memory,
        max_steps=3,
    )

    record = orchestrator.run_one()

    assert record.backend == "mock"
    assert record.evaluation.task_success is True
    assert record.evaluation.environmental_failure is True
    assert record.evaluation.failure_type == "structural_collapse"
    assert record.evaluation.severity is Severity.HIGH
    assert record.evaluation.metrics["step_count"] == 2
    assert len(memory) == 1
    assert memory.summaries()[0].trajectory_ref == record.trajectory_ref

    trajectory_path = Path(record.trajectory_ref)
    lines = [json.loads(line) for line in trajectory_path.read_text(encoding="utf-8").splitlines()]
    assert [line["record_type"] for line in lines] == ["initial_observation", "step", "step"]
    result = json.loads((trajectory_path.parent / "result.json").read_text(encoding="utf-8"))
    assert result["environmental_failure"] is True


def test_second_scenario_proposal_receives_compact_memory(tmp_path: Path):
    scenario_agent = StaticScenarioAgent(
        Scenario(environment="mock", task="reach", parameters={"target_position": 1})
    )
    orchestrator = Orchestrator(
        MockEnvironment(),
        scenario_agent,
        MockRobotController(),
        RuleBasedEvaluator(),
        TrajectoryRecorder(tmp_path / "runs"),
    )

    orchestrator.run_one()
    orchestrator.run_one()

    assert len(scenario_agent.seen_memory) == 1
    assert scenario_agent.seen_memory[0].task_success is True
