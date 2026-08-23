"""Generate a bounded world-model conditioning prompt from Isaac evidence."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class WorldPromptError(ValueError):
    """Raised when a world-model prompt cannot be safely created."""


@dataclass(frozen=True, slots=True)
class WorldPromptRequest:
    """Structured, non-executable context for one visual world-model prompt."""

    initial_frame_path: str | Path
    task: str
    seed: int
    isaac_parameters: dict[str, Any]
    isaac_hazards: dict[str, Any]
    objective: str = ""

    def __post_init__(self) -> None:
        path = Path(self.initial_frame_path)
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise WorldPromptError("initial_frame_path must be an existing PNG, JPEG, or WEBP image")
        if path.stat().st_size > 10 * 1024 * 1024:
            raise WorldPromptError("initial frame must not exceed 10 MiB")
        if not isinstance(self.task, str) or not self.task.strip():
            raise WorldPromptError("task must be a non-empty string")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise WorldPromptError("seed must be an integer")
        object.__setattr__(self, "initial_frame_path", path)


@dataclass(frozen=True, slots=True)
class WorldPromptResult:
    prompt: str
    response_id: str | None


class OpenAIResponsesWorldPromptModel:
    """Make one scene-conditioning prompt; it has no simulator or shell access."""

    def __init__(self, model: str, client: Any | None = None, *, max_output_tokens: int = 300) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("a Responses API model ID is required")
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise RuntimeError("install the 'research' extra to use the OpenAI provider") from error
            client = OpenAI()
        self.model, self.client = model, client
        self.max_output_tokens = max_output_tokens

    def create_prompt(self, request: WorldPromptRequest) -> WorldPromptResult:
        context = {
            "task": request.task,
            "seed": request.seed,
            "isaac_parameters": request.isaac_parameters,
            "isaac_hazards": request.isaac_hazards,
            "objective": request.objective,
        }
        response = self.client.responses.create(
            model=self.model,
            instructions=(
                "Create one concise scene-conditioning prompt for a generative visual world model. "
                "Use the supplied image and structured Isaac context. Describe only visible scene "
                "elements and the requested experiment. Do not claim physics certainty, issue commands, "
                "or include code."
            ),
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": json.dumps(context, sort_keys=True)},
                        {"type": "input_image", "image_url": _data_url(request.initial_frame_path), "detail": "low"},
                    ],
                }
            ],
            store=True,
            max_output_tokens=self.max_output_tokens,
            reasoning={"effort": "low"},
            text={"format": {"type": "json_schema", "name": "world_model_prompt", "strict": True, "schema": _PROMPT_SCHEMA}},
        )
        try:
            prompt = json.loads(response.output_text)["prompt"]
        except (AttributeError, KeyError, json.JSONDecodeError, TypeError) as error:
            raise WorldPromptError("Responses API did not return a valid world-model prompt") from error
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2_000:
            raise WorldPromptError("world-model prompt must be a non-empty string of at most 2000 characters")
        return WorldPromptResult(prompt.strip(), getattr(response, "id", None))


def _data_url(path: Path) -> str:
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[path.suffix.lower()]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


_PROMPT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["prompt"],
    "properties": {"prompt": {"type": "string", "maxLength": 2000}},
}
