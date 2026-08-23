"""Validated, non-executable experiment representations for research models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any


class ResearchProposalError(ValueError):
    """Raised when a research proposal cannot be represented safely."""


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchProposalError(f"{name} must be a non-empty string")
    return value.strip()


def _mapping(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchProposalError(f"{name} must be a mapping")
    return dict(value)


@dataclass(frozen=True, slots=True)
class ExperimentIntent:
    """The backend-neutral semantic task a model wants to investigate."""

    task: str
    seed: int

    def __post_init__(self) -> None:
        _text(self.task, "task")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ResearchProposalError("seed must be an integer")


@dataclass(frozen=True, slots=True)
class ExperimentProposal:
    """A bounded proposal; it intentionally contains neither code nor transport calls."""

    hypothesis: str
    rationale_summary: str
    focus: str
    experiment_intent: ExperimentIntent
    parameter_changes: Mapping[str, Any] = field(default_factory=dict)
    world_edits: tuple[Mapping[str, Any], ...] = ()
    expected_information_gain: str = "medium"

    def __post_init__(self) -> None:
        for value, name in ((self.hypothesis, "hypothesis"), (self.rationale_summary, "rationale_summary"),
                            (self.focus, "focus"), (self.expected_information_gain, "expected_information_gain")):
            _text(value, name)
        if not isinstance(self.experiment_intent, ExperimentIntent):
            raise ResearchProposalError("experiment_intent must be an ExperimentIntent")
        object.__setattr__(self, "parameter_changes", _mapping(self.parameter_changes, "parameter_changes"))
        edits = tuple(self.world_edits)
        if not all(isinstance(edit, Mapping) for edit in edits):
            raise ResearchProposalError("world_edits must contain mappings")
        for edit in edits:
            _reject_executable_fields(edit)
        object.__setattr__(self, "world_edits", tuple(dict(edit) for edit in edits))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ExperimentProposal:
        try:
            intent = value["experiment_intent"]
            changes = value.get("parameter_changes", {})
            if isinstance(changes, list):
                changes = {entry["name"]: entry["value"] for entry in changes}
            return cls(
                hypothesis=value["hypothesis"], rationale_summary=value["rationale_summary"],
                focus=value["focus"], experiment_intent=ExperimentIntent(task=intent["task"], seed=intent["seed"]),
                parameter_changes=changes, world_edits=tuple(value.get("world_edits", ())),
                expected_information_gain=value.get("expected_information_gain", "medium"),
            )
        except (KeyError, TypeError) as error:
            raise ResearchProposalError("proposal is missing a required structured field") from error


def _reject_executable_fields(value: Mapping[str, Any]) -> None:
    """Keep proposals declarative even before capability validation rejects them.

    This is deliberately a deny-list in addition to the worker's allow-list:
    the initial verified capability set accepts no world operations at all.
    """
    prohibited = {"code", "python", "script", "command", "shell", "source"}
    for key, item in value.items():
        if str(key).casefold() in prohibited:
            raise ResearchProposalError("world edits may not contain executable-code fields")
        if isinstance(item, Mapping):
            _reject_executable_fields(item)
