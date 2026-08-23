"""Compile validated research intent into existing harness scenario types."""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from harness.comparison.plan_c import ActionAlignment, MatchedExperimentSpec
from harness.research.schemas import ExperimentProposal
from harness.research.search_space import WorldCapabilities
from harness.schemas import Scenario


@dataclass(frozen=True, slots=True)
class CompiledExperiment:
    proposal: ExperimentProposal
    isaac_scenario: Scenario
    matched_experiment: MatchedExperimentSpec | None
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScenarioCompiler:
    """The mandatory validation boundary between a research model and backends."""

    def compile(self, proposal: ExperimentProposal, capabilities: WorldCapabilities) -> CompiledExperiment:
        changes = capabilities.validate_changes(proposal.parameter_changes, proposal.world_edits)
        parameters = {name: value for name, value in changes.items() if name != "collapse_after_actions"}
        hazards = {name: value for name, value in changes.items() if name == "collapse_after_actions"}
        if "collapse_after_actions" in hazards:
            # The reference hazard run must terminate, preventing an ambiguous
            # long-running worker request after support release.
            hazards["terminal_on_collapse"] = True
        intent = proposal.experiment_intent
        capabilities.validate_task(intent.task)
        isaac = Scenario(environment="isaac_sim", task=intent.task, seed=intent.seed, parameters=parameters, hazards=hazards)
        matched = None
        if capabilities.reactor_model:
            reactor = Scenario(environment=f"reactor/{capabilities.reactor_model}", task=intent.task, seed=intent.seed)
            matched = MatchedExperimentSpec(
                task=intent.task, seed=intent.seed, isaac_scenario=isaac, neural_scenario=reactor,
                action_alignment=ActionAlignment.SEMANTIC,
                alignment_note="Isaac planar velocity and Reactor visual steering require semantic alignment.",
            )
        return CompiledExperiment(
            proposal,
            isaac,
            matched,
            {
                "compiler": "isaac_v0",
                "capability_version": capabilities.version,
                "capability_parameters": sorted(capabilities.parameters),
                "repository_git_sha": _repository_git_sha(),
            },
        )


def _repository_git_sha() -> str | None:
    root = Path(__file__).resolve().parents[3]
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
