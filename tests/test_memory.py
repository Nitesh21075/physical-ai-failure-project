from datetime import UTC, datetime

from harness.memory import ExperimentMemory
from harness.schemas import EvaluationResult, ExperimentRecord, Scenario, Severity


def _record(run_id: str) -> ExperimentRecord:
    return ExperimentRecord(
        run_id=run_id,
        scenario=Scenario(scenario_id=run_id, environment="mock", task="reach"),
        backend="mock",
        trajectory_ref=f"/runs/{run_id}/trajectory.jsonl",
        evaluation=EvaluationResult(
            task_success=True,
            environmental_failure=False,
            failure_type=None,
            severity=Severity.NONE,
            metrics={"step_count": 1},
        ),
        created_at=datetime.now(UTC).isoformat(),
    )


def test_experiment_memory_is_bounded_and_contains_summaries_only():
    memory = ExperimentMemory(capacity=2)
    for run_id in ("run-1", "run-2", "run-3"):
        memory.add(_record(run_id))

    summaries = memory.summaries()
    assert [summary.run_id for summary in summaries] == ["run-2", "run-3"]
    assert "trajectory" not in summaries[-1].to_dict()
