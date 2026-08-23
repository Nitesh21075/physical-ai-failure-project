"""Compact, database-backed context for one research-model turn."""

from __future__ import annotations

import json
from typing import Any

from harness.research.campaign import ResearchCampaignStore
from harness.research.search_space import WorldCapabilities


def build_research_context(store: ResearchCampaignStore, campaign_id: str, capabilities: WorldCapabilities) -> dict[str, Any]:
    campaign = store.get_campaign(campaign_id)
    if campaign is None:
        raise KeyError(f"unknown campaign: {campaign_id}")
    prior = []
    for iteration in store.incomplete_iterations(campaign_id):
        if iteration["proposal_json"]:
            proposal = json.loads(iteration["proposal_json"])
            prior.append({"state": iteration["state"], "parameter_changes": proposal.get("parameter_changes", {}), "hypothesis": proposal.get("hypothesis", "")})
    return {
        "objective": campaign["objective"], "constraints": campaign["constraints"],
        "budget_remaining": campaign["experiment_budget"] - campaign["experiments_used"],
        "capabilities": {"tasks": capabilities.supported_tasks, "parameters": {name: spec.description for name, spec in capabilities.parameters.items()}, "world_operations": capabilities.supported_world_operations},
        "operator_instructions": store.pending_instructions(campaign_id), "recent_iterations": prior[-8:],
    }
