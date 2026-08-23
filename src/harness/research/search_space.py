"""Capability registry exposed to a research model and compiler."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from harness.research.schemas import ResearchProposalError


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    name: str
    kind: Literal["float", "int", "vector"]
    minimum: float | None = None
    maximum: float | None = None
    dimensions: int | None = None
    description: str = ""

    def validate(self, value: Any) -> Any:
        if self.kind == "vector":
            if not isinstance(value, (list, tuple)) or len(value) != self.dimensions:
                raise ResearchProposalError(f"{self.name} must be a {self.dimensions}-value numeric vector")
            return [self._number(item) for item in value]
        if self.kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ResearchProposalError(f"{self.name} must be an integer")
            result: float | int = value
        else:
            result = self._number(value)
        if self.minimum is not None and result < self.minimum or self.maximum is not None and result > self.maximum:
            raise ResearchProposalError(f"{self.name} is outside its allowed range")
        return result

    def _number(self, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ResearchProposalError(f"{self.name} must contain only numeric values")
        return float(value)


@dataclass(frozen=True, slots=True)
class WorldCapabilities:
    parameters: Mapping[str, ParameterSpec]
    supported_tasks: tuple[str, ...] = ("reach_target",)
    supported_world_operations: tuple[str, ...] = ()
    reactor_model: str | None = None
    version: str = "isaac_v0"

    def validate_changes(self, changes: Mapping[str, Any], world_edits: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
        unknown = set(changes).difference(self.parameters)
        if unknown:
            raise ResearchProposalError(f"unsupported parameters: {', '.join(sorted(unknown))}")
        if world_edits:
            raise ResearchProposalError("world edits are not enabled by the verified Isaac v0 capability set")
        return {name: self.parameters[name].validate(value) for name, value in changes.items()}

    def validate_task(self, task: str) -> None:
        if task not in self.supported_tasks:
            raise ResearchProposalError(f"unsupported task: {task}")


def isaac_v0_capabilities(*, reactor_model: str | None = None) -> WorldCapabilities:
    """Only the parameters actually accepted by ``IsaacSimEnvironment`` today."""
    return WorldCapabilities(
        parameters={
            "target_position": ParameterSpec("target_position", "vector", dimensions=2, description="Robot goal x/y."),
            "robot_start": ParameterSpec("robot_start", "vector", dimensions=3, description="Robot start x/y/z."),
            "physics_steps_per_action": ParameterSpec("physics_steps_per_action", "int", minimum=1, maximum=600, description="Bounded physics frames per action."),
            "collapse_after_actions": ParameterSpec("collapse_after_actions", "int", minimum=1, maximum=1000, description="Action number that releases the support beam."),
        },
        reactor_model=reactor_model,
    )
