"""One bounded, recoverable research turn; execution is coordinated elsewhere."""

from __future__ import annotations

from harness.research.campaign import IterationState, ResearchCampaignStore
from harness.research.compiler import CompiledExperiment, ScenarioCompiler
from harness.research.context import build_research_context
from harness.research.model import ResearchModel
from harness.research.schemas import ResearchProposalError
from harness.research.search_space import WorldCapabilities


class ResearchAgent:
    """Build, propose, validate, and compile exactly one campaign iteration."""

    def __init__(
        self,
        store: ResearchCampaignStore,
        model: ResearchModel,
        compiler: ScenarioCompiler,
        capabilities: WorldCapabilities,
    ) -> None:
        self.store, self.model = store, model
        self.compiler, self.capabilities = compiler, capabilities

    def propose_one(self, campaign_id: str) -> tuple[str, CompiledExperiment]:
        campaign = self.store.get_campaign(campaign_id)
        if campaign is None:
            raise KeyError(f"unknown campaign: {campaign_id}")
        if campaign["experiments_used"] >= campaign["experiment_budget"]:
            raise RuntimeError("campaign experiment budget is exhausted")
        context = build_research_context(self.store, campaign_id, self.capabilities)
        iteration_id = self.store.begin_iteration(campaign_id, context)
        self.store.transition_iteration(iteration_id, IterationState.THINKING)
        result = self.model.propose_next_experiment(context, previous_response_id=campaign["last_openai_response_id"])
        self.store.transition_iteration(iteration_id, IterationState.PROPOSAL_RECEIVED, proposal=result.proposal.to_dict(), response_id=result.response_id)
        self.store.transition_iteration(iteration_id, IterationState.VALIDATING)
        try:
            if self.store.has_equivalent_proposal(campaign_id, result.proposal.to_dict(), exclude_iteration_id=iteration_id):
                raise ResearchProposalError("proposal duplicates an already-tested or pending parameter configuration")
            compiled = self.compiler.compile(result.proposal, self.capabilities)
        except ResearchProposalError as error:
            self.store.transition_iteration(iteration_id, IterationState.FAILED, error=str(error))
            raise
        self.store.transition_iteration(iteration_id, IterationState.COMPILED, compiled=compiled.to_dict())
        self.store.set_last_response_id(campaign_id, result.response_id)
        self.store.consume_instructions(campaign_id)
        return iteration_id, compiled
