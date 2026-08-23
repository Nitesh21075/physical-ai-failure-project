"""OpenAI Responses API adapter with strict JSON output and no runtime tools."""

from __future__ import annotations

import json
from typing import Any

from harness.research.model import ResearchModelResult
from harness.research.schemas import ExperimentProposal, ResearchProposalError


class OpenAIResponsesResearchModel:
    """Proposes a single bounded experiment; the host validates it afterwards."""

    def __init__(
        self, model: str, client: Any | None = None, *, max_output_tokens: int = 800,
        reasoning_effort: str = "low",
    ) -> None:
        if not model.strip():
            raise ValueError("a Responses API model ID is required")
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise RuntimeError("install the 'research' extra to use the OpenAI provider") from error
            client = OpenAI()
        if max_output_tokens < 64:
            raise ValueError("max_output_tokens must be at least 64")
        self.model, self.client = model, client
        self.max_output_tokens, self.reasoning_effort = max_output_tokens, reasoning_effort

    def propose_next_experiment(
        self, context: dict, *, previous_response_id: str | None = None
    ) -> ResearchModelResult:
        request: dict[str, Any] = {
            "model": self.model,
            "instructions": (
                "You are an experiment-level physical-AI researcher. Return one controlled "
                "proposal only. Do not emit code, shell commands, world-model claims, or tools. "
                "Use only capabilities supplied in the context."
            ),
            "input": json.dumps(context, sort_keys=True),
            "store": True,
            "max_output_tokens": self.max_output_tokens,
            "reasoning": {"effort": self.reasoning_effort},
            "text": {"format": {"type": "json_schema", "name": "experiment_proposal", "strict": True, "schema": _PROPOSAL_SCHEMA}},
        }
        if previous_response_id:
            request["previous_response_id"] = previous_response_id
        response = self.client.responses.create(**request)
        try:
            proposal = ExperimentProposal.from_dict(json.loads(response.output_text))
        except (AttributeError, json.JSONDecodeError, ResearchProposalError) as error:
            raise ResearchProposalError("Responses API did not return a valid experiment proposal") from error
        return ResearchModelResult(proposal=proposal, response_id=getattr(response, "id", None))


_PROPOSAL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["hypothesis", "rationale_summary", "focus", "experiment_intent", "parameter_changes", "world_edits", "expected_information_gain"],
    "properties": {
        "hypothesis": {"type": "string"}, "rationale_summary": {"type": "string"},
        "focus": {"type": "string"}, "expected_information_gain": {"type": "string"},
        "experiment_intent": {"type": "object", "additionalProperties": False, "required": ["task", "seed"], "properties": {"task": {"type": "string", "enum": ["reach_target"]}, "seed": {"type": "integer"}}},
        "parameter_changes": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["name", "value"], "properties": {"name": {"type": "string", "enum": ["target_position", "robot_start", "physics_steps_per_action", "collapse_after_actions"]}, "value": {"anyOf": [{"type": "number"}, {"type": "integer"}, {"type": "array", "items": {"type": "number"}}]}}}},
        "world_edits": {"type": "array", "maxItems": 0, "items": {"type": "object", "additionalProperties": False, "properties": {}}},
    },
}
