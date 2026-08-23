from harness.isaac_worker import IsaacWorker
from harness.schemas import EvaluationResult, ExperimentRecord, Scenario, Severity


class FakeRunner:
    def __init__(self) -> None:
        self.closed = False

    def run(self, scenario: Scenario) -> ExperimentRecord:
        return ExperimentRecord("run-1", scenario, "isaac_sim", "/runs/run-1/trajectory.jsonl", EvaluationResult(False, True, "structural_collapse", Severity.HIGH), "2026-01-01T00:00:00+00:00")

    def close(self) -> None:
        self.closed = True


def envelope(**values):
    return {"request_id": "request-1", "schema_version": "v1", **values}


def test_worker_advertises_only_verified_capabilities_and_runs_a_typed_scenario(tmp_path):
    runner = FakeRunner(); worker = IsaacWorker(tmp_path, runner)
    assert worker.handle("GET", "/health")["result"]["status"] == "ready"
    assert worker.handle("GET", "/capabilities", envelope())["result"]["world_operations"] == []
    scenario = Scenario("isaac_sim", "reach_target", hazards={"collapse_after_actions": 2})
    result = worker.handle("POST", "/experiment/run", envelope(campaign_id="campaign-1", iteration_id="iteration-1", experiment={"isaac_scenario": scenario.to_dict()}))
    assert result["result"]["run_id"] == "run-1"
    assert worker.handle("POST", "/experiment/run", envelope(campaign_id="campaign-1", iteration_id="iteration-1", experiment={"isaac_scenario": scenario.to_dict()}))["result"]["run_id"] == "run-1"
    assert worker.handle("GET", "/experiment/status/run-1", envelope())["result"]["status"] == "completed"


def test_worker_rejects_bad_envelopes_and_never_exposes_arbitrary_world_edits(tmp_path):
    worker = IsaacWorker(tmp_path, FakeRunner())
    assert worker.handle("GET", "/capabilities", {})["error"]["code"] == "UNSUPPORTED_SCHEMA"
    response = worker.handle("POST", "/experiment/run", envelope(campaign_id="c", iteration_id="i", experiment={"world_edits": [{"op": "python"}]}))
    assert response["error"]["code"] == "INVALID_EXPERIMENT"


def test_queue_mode_defers_work_to_the_main_thread(tmp_path):
    worker = IsaacWorker(tmp_path, FakeRunner(), queue_requests=True)
    holder = {}
    def submit_health(): holder["response"] = worker.submit("GET", "/health", {})
    import threading
    thread = threading.Thread(target=submit_health); thread.start()
    assert worker.process_next(timeout=1) is True
    thread.join(timeout=1)
    assert holder["response"]["result"]["status"] == "ready"
