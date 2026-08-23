import json

from PIL import Image

from harness.persistence import ExperimentStore
from harness.research import (
    AssetCatalogError,
    CampaignExecutor,
    ExperimentProposal,
    ResearchAgent,
    ResearchCampaignStore,
    ScenarioCompiler,
    isaac_v0_asset_catalog,
    isaac_v0_capabilities,
)
from harness.research.model import ResearchModelResult
from harness.research.openai_responses import OpenAIResponsesResearchModel
from harness.research.schemas import ExperimentIntent, ResearchProposalError
from harness.research.visual_assessment import (
    OpenAIResponsesVisualAssessor,
    VisualComparisonRequest,
)
from harness.schemas import EvaluationResult, ExperimentRecord, Severity


def proposal(**changes):
    return ExperimentProposal("Support release becomes likely after repeated movement.", "Probe the known bounded hazard.", "failure_boundary", ExperimentIntent("reach_target", 7), changes)


def test_compiler_uses_only_verified_isaac_parameters_and_can_make_a_plan_c_pair():
    compiled = ScenarioCompiler().compile(proposal(collapse_after_actions=2, physics_steps_per_action=24), isaac_v0_capabilities(reactor_model="lingbot"))
    assert compiled.isaac_scenario.hazards == {"collapse_after_actions": 2, "terminal_on_collapse": True}
    assert compiled.isaac_scenario.parameters["physics_steps_per_action"] == 24
    assert compiled.matched_experiment is not None
    assert compiled.matched_experiment.neural_scenario.environment == "reactor/lingbot"


def test_compiler_rejects_unverified_changes_and_world_edits():
    compiler = ScenarioCompiler()
    try:
        compiler.compile(proposal(robot_speed_mps=0.85), isaac_v0_capabilities())
    except ResearchProposalError as error:
        assert "unsupported parameters" in str(error)
    else: raise AssertionError("unsupported parameter was accepted")
    invalid = ExperimentProposal("h", "r", "f", ExperimentIntent("reach_target", 7), world_edits=({"op": "spawn_asset"},))
    try:
        compiler.compile(invalid, isaac_v0_capabilities())
    except ResearchProposalError as error:
        assert "world edits" in str(error)
    else: raise AssertionError("world edit was accepted")
    try:
        compiler.compile(ExperimentProposal("h", "r", "f", ExperimentIntent("invented_task", 7)), isaac_v0_capabilities())
    except ResearchProposalError as error:
        assert "unsupported task" in str(error)
    else: raise AssertionError("unsupported task was accepted")
    try:
        ExperimentProposal("h", "r", "f", ExperimentIntent("reach_target", 7), world_edits=({"op": "set_pose", "python": "import os"},))
    except ResearchProposalError as error:
        assert "executable-code" in str(error)
    else: raise AssertionError("executable world edit was accepted")


def test_asset_catalog_never_exposes_the_container_filesystem():
    catalog = isaac_v0_asset_catalog()
    assert catalog.list_asset_categories() == ()
    assert catalog.search_assets("any") == ()
    try:
        catalog.inspect_asset("/workspace/project/secret.usd")
    except AssetCatalogError as error:
        assert error.code == "ASSET_NOT_AVAILABLE"
    else: raise AssertionError("unknown filesystem path was treated as an asset")


def test_campaign_memory_survives_store_reopen(tmp_path):
    database = tmp_path / "research.sqlite3"
    campaign_id = ResearchCampaignStore(database).create_campaign("Find collapse boundary", experiment_budget=2, constraints={"max_speed": 1})
    ResearchCampaignStore(database).add_instruction(campaign_id, "Use low speeds.")
    reopened = ResearchCampaignStore(database)
    assert reopened.get_campaign(campaign_id)["objective"] == "Find collapse boundary"
    assert reopened.pending_instructions(campaign_id) == ["Use low speeds."]


def test_campaign_persists_capability_and_simulator_provenance(tmp_path):
    store = ResearchCampaignStore(tmp_path / "research.sqlite3")
    campaign_id = store.create_campaign(
        "Find collapse boundary", experiment_budget=1, capability_version="isaac_v0",
        simulator_metadata={"container_image": "nvcr.io/nvidia/isaac-sim:6.0.1"},
    )
    restored = ResearchCampaignStore(tmp_path / "research.sqlite3").get_campaign(campaign_id)
    assert restored["capability_version"] == "isaac_v0"
    assert restored["simulator_metadata"]["container_image"].endswith("6.0.1")


def test_iteration_state_is_durable_and_tracks_the_openai_response(tmp_path):
    store = ResearchCampaignStore(tmp_path / "research.sqlite3")
    campaign_id = store.create_campaign("Find collapse boundary", experiment_budget=2)
    iteration_id = store.begin_iteration(campaign_id, {"objective": "Find collapse boundary"})
    store.transition_iteration(iteration_id, "proposal_received", proposal=proposal().to_dict(), response_id="resp_1")
    recovered = ResearchCampaignStore(tmp_path / "research.sqlite3").incomplete_iterations(campaign_id)
    assert recovered[0]["state"] == "proposal_received"
    assert recovered[0]["openai_response_id"] == "resp_1"


def test_openai_provider_uses_strict_structured_output_without_tools():
    captured = {}
    class Responses:
        def create(self, **request):
            captured.update(request)
            return type("Response", (), {"id": "resp_1", "output_text": json.dumps(proposal().to_dict())})()
    model = OpenAIResponsesResearchModel("test-model", type("Client", (), {"responses": Responses()})())
    result = model.propose_next_experiment({"capabilities": {}}, previous_response_id="resp_previous")
    assert result.response_id == "resp_1"
    assert captured["previous_response_id"] == "resp_previous"
    assert captured["text"]["format"]["strict"] is True
    assert captured["max_output_tokens"] == 800
    assert captured["reasoning"]["effort"] == "low"
    assert "tools" not in captured


def test_visual_assessor_sends_both_sources_as_labeled_structured_image_input(tmp_path):
    captured = {}

    class Responses:
        def create(self, **request):
            captured.update(request)
            return type("Response", (), {"output_text": '{"isaac_observed": true, "world_model_observed": true, "world_model_confidence": 0.8}'})()

    first, second = tmp_path / "first.png", tmp_path / "second.png"
    Image.new("RGB", (2, 2), "red").save(first)
    Image.new("RGB", (2, 2), "blue").save(second)
    assessment = OpenAIResponsesVisualAssessor(
        "vision-model", type("Client", (), {"responses": Responses()})()
    ).assess(VisualComparisonRequest("structural_collapse", (first,), (second,)))

    content = captured["input"][0]["content"]
    assert [item["type"] for item in content] == ["input_text", "input_image", "input_text", "input_image"]
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert "Isaac/PhysX" in content[0]["text"]
    assert "Neural world-model" in content[2]["text"]
    assert captured["text"]["format"]["strict"] is True
    assert assessment.isaac_observed is True
    assert assessment.world_model_assessment.observed is True
    assert assessment.world_model_assessment.assessor == "openai_responses/vision-model"


def test_agent_persists_a_single_compiled_turn_and_response_chain(tmp_path):
    class FakeModel:
        def propose_next_experiment(self, context, *, previous_response_id=None):
            assert context["budget_remaining"] == 2
            assert previous_response_id is None
            return ResearchModelResult(proposal(collapse_after_actions=2), "resp_1")
    store = ResearchCampaignStore(tmp_path / "research.sqlite3")
    campaign_id = store.create_campaign("Find collapse boundary", experiment_budget=2)
    iteration_id, compiled = ResearchAgent(store, FakeModel(), ScenarioCompiler(), isaac_v0_capabilities()).propose_one(campaign_id)
    assert compiled.isaac_scenario.hazards == {"collapse_after_actions": 2, "terminal_on_collapse": True}
    assert store.get_campaign(campaign_id)["last_openai_response_id"] == "resp_1"
    assert store.incomplete_iterations(campaign_id)[0]["iteration_id"] == iteration_id


def test_agent_rejects_duplicate_parameter_proposal(tmp_path):
    class FakeModel:
        def propose_next_experiment(self, context, *, previous_response_id=None):
            return ResearchModelResult(proposal(collapse_after_actions=2), "resp_1")
    store = ResearchCampaignStore(tmp_path / "research.sqlite3")
    campaign_id = store.create_campaign("Find collapse boundary", experiment_budget=2)
    agent = ResearchAgent(store, FakeModel(), ScenarioCompiler(), isaac_v0_capabilities())
    agent.propose_one(campaign_id)
    try:
        agent.propose_one(campaign_id)
    except ResearchProposalError as error:
        assert "duplicates" in str(error)
    else: raise AssertionError("duplicate proposal was accepted")


def test_campaign_executor_records_one_isaac_run_and_consumes_budget(tmp_path):
    class FakeModel:
        def propose_next_experiment(self, context, *, previous_response_id=None):
            return ResearchModelResult(proposal(collapse_after_actions=2), "resp_1")
    class FakeIsaac:
        def run_experiment(self, compiled_experiment, *, campaign_id, iteration_id):
            record = ExperimentRecord("run-1", compiled_experiment.isaac_scenario, "isaac_sim", "/runs/run-1/trajectory.jsonl", EvaluationResult(False, True, "structural_collapse", Severity.HIGH), "2026-01-01T00:00:00+00:00")
            return {"run_id": "run-1", "record": record.to_dict()}
    research = ResearchCampaignStore(tmp_path / "research.sqlite3")
    campaign_id = research.create_campaign("Find collapse boundary", experiment_budget=1)
    agent = ResearchAgent(research, FakeModel(), ScenarioCompiler(), isaac_v0_capabilities())
    iteration_id = CampaignExecutor(research, ExperimentStore(tmp_path / "experiments.sqlite3"), agent, FakeIsaac()).run_one_isaac_iteration(campaign_id)
    assert research.get_iteration(iteration_id)["state"] == "recorded"
    assert research.get_campaign(campaign_id)["status"] == "completed"


def test_campaign_executor_recovers_authoritative_run_after_client_timeout(tmp_path):
    class FakeModel:
        def propose_next_experiment(self, context, *, previous_response_id=None):
            return ResearchModelResult(proposal(collapse_after_actions=2), "resp_1")
    class LostResponseIsaac:
        def run_experiment(self, compiled_experiment, *, campaign_id, iteration_id):
            run = tmp_path / "runs" / "worker" / "run-1"; run.mkdir(parents=True)
            (run / "scenario.json").write_text(json.dumps(compiled_experiment.isaac_scenario.to_dict()))
            (run / "metadata.json").write_text(json.dumps({"run_id": "run-1", "backend": "isaac_sim"}))
            (run / "result.json").write_text(json.dumps(EvaluationResult(False, True, "structural_collapse", Severity.HIGH).to_dict()))
            (run / "trajectory.jsonl").write_text("")
            raise TimeoutError("response lost")
    research = ResearchCampaignStore(tmp_path / "research.sqlite3")
    campaign_id = research.create_campaign("Find collapse boundary", experiment_budget=1)
    agent = ResearchAgent(research, FakeModel(), ScenarioCompiler(), isaac_v0_capabilities())
    iteration_id = CampaignExecutor(research, ExperimentStore(tmp_path / "experiments.sqlite3"), agent, LostResponseIsaac(), runs_root=tmp_path / "runs").run_one_isaac_iteration(campaign_id)
    assert research.get_iteration(iteration_id)["state"] == "recorded"
    assert research.get_campaign(campaign_id)["status"] == "completed"
