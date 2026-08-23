"""The narrow runtime model contract; implementations never run experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from harness.research.schemas import ExperimentProposal


@dataclass(frozen=True, slots=True)
class ResearchModelResult:
    proposal: ExperimentProposal
    response_id: str | None = None


class ResearchModel(Protocol):
    def propose_next_experiment(
        self, context: dict, *, previous_response_id: str | None = None
    ) -> ResearchModelResult: ...
