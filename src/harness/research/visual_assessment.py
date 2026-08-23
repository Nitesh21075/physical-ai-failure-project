"""Responses-based visual evidence assessment.

This adapter judges only what is visible in a small set of persisted image
frames. It deliberately does not infer simulator state or establish physical
ground truth; :class:`VisualEventAssessment` keeps that boundary explicit.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.comparison.plan_c import VisualEventAssessment


class VisualAssessmentError(ValueError):
    """Raised when visual evidence or a model response is not usable."""


_MIME_TYPES = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


@dataclass(frozen=True, slots=True)
class VisualComparisonRequest:
    """A bounded visual comparison of Isaac reference and world-model frames."""

    event_type: str
    isaac_frame_paths: tuple[str | Path, ...]
    world_model_frame_paths: tuple[str | Path, ...]
    detail: str = "low"

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise VisualAssessmentError("event_type must be a non-empty string")
        isaac_paths = tuple(Path(path) for path in self.isaac_frame_paths)
        world_model_paths = tuple(Path(path) for path in self.world_model_frame_paths)
        if not 1 <= len(isaac_paths) <= 4:
            raise VisualAssessmentError("provide between one and four Isaac image frames")
        if not 1 <= len(world_model_paths) <= 4:
            raise VisualAssessmentError("provide between one and four world-model image frames")
        if self.detail not in {"low", "high", "auto"}:
            raise VisualAssessmentError("detail must be low, high, or auto")
        for path in (*isaac_paths, *world_model_paths):
            if not path.is_file():
                raise VisualAssessmentError(f"frame does not exist: {path}")
            if path.suffix.lower() not in _MIME_TYPES:
                raise VisualAssessmentError(f"unsupported image format: {path.suffix}")
            if path.stat().st_size > 10 * 1024 * 1024:
                raise VisualAssessmentError(f"frame is larger than 10 MiB: {path}")
        object.__setattr__(self, "isaac_frame_paths", isaac_paths)
        object.__setattr__(self, "world_model_frame_paths", world_model_paths)


@dataclass(frozen=True, slots=True)
class VisualComparisonAssessment:
    """The model's visual reading of both sources, never physical ground truth."""

    isaac_observed: bool | None
    world_model_assessment: VisualEventAssessment

    def __post_init__(self) -> None:
        if self.isaac_observed is not None and not isinstance(self.isaac_observed, bool):
            raise VisualAssessmentError("isaac_observed must be a boolean or null")

    def to_dict(self) -> dict[str, Any]:
        return {
            "isaac_observed": self.isaac_observed,
            "world_model_assessment": self.world_model_assessment.to_dict(),
        }


class OpenAIResponsesVisualAssessor:
    """Obtain non-authoritative visual evidence from a Responses vision model."""

    def __init__(
        self,
        model: str,
        client: Any | None = None,
        *,
        max_output_tokens: int = 400,
        reasoning_effort: str = "low",
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("a Responses API model ID is required")
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise RuntimeError("install the 'research' extra to use the OpenAI provider") from error
            client = OpenAI()
        if max_output_tokens < 64:
            raise ValueError("max_output_tokens must be at least 64")
        self.model = model
        self.client = client
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort

    def assess(self, request: VisualComparisonRequest) -> VisualComparisonAssessment:
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": f"Isaac/PhysX reference frames, ordered earliest to latest, for `{request.event_type}`:",
            }
        ]
        content.extend(_image_input(path, request.detail) for path in request.isaac_frame_paths)
        content.append(
            {
                "type": "input_text",
                "text": "Neural world-model frames, ordered earliest to latest, for the same declared event:",
            }
        )
        content.extend(_image_input(path, request.detail) for path in request.world_model_frame_paths)
        response = self.client.responses.create(
            model=self.model,
            instructions=(
                "You are a visual evidence assessor. Judge pixels only; do not claim physical "
                "ground truth, infer hidden state, or make causal claims. A null observation is "
                "required when the evidence cannot support a visual decision."
            ),
            input=[{"role": "user", "content": content}],
            store=True,
            max_output_tokens=self.max_output_tokens,
            reasoning={"effort": self.reasoning_effort},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "visual_event_assessment",
                    "strict": True,
                    "schema": _ASSESSMENT_SCHEMA,
                }
            },
        )
        try:
            output = json.loads(response.output_text)
            isaac_observed = output["isaac_observed"]
            world_model_observed = output["world_model_observed"]
            confidence = output["world_model_confidence"]
            if isaac_observed is not None and not isinstance(isaac_observed, bool):
                raise TypeError("isaac_observed must be a boolean or null")
            if world_model_observed is not None and not isinstance(world_model_observed, bool):
                raise TypeError("world_model_observed must be a boolean or null")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise TypeError("world_model_confidence must be numeric")
            return VisualComparisonAssessment(
                isaac_observed=isaac_observed,
                world_model_assessment=VisualEventAssessment(
                    event_type=request.event_type,
                    observed=world_model_observed,
                    confidence=float(confidence),
                    evidence_refs=tuple(str(path) for path in request.world_model_frame_paths),
                    assessor=f"openai_responses/{self.model}",
                ),
            )
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise VisualAssessmentError("Responses API did not return a valid visual assessment") from error


def _data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{_MIME_TYPES[path.suffix.lower()]};base64,{encoded}"


def _image_input(path: Path, detail: str) -> dict[str, str]:
    return {"type": "input_image", "image_url": _data_url(path), "detail": detail}


_ASSESSMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["isaac_observed", "world_model_observed", "world_model_confidence"],
    "properties": {
        "isaac_observed": {"type": ["boolean", "null"]},
        "world_model_observed": {"type": ["boolean", "null"]},
        "world_model_confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}
