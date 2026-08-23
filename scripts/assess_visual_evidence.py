"""Assess selected saved image frames with the Responses API.

This creates a visual-only assessment; it is not a physical simulation result.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from harness.research.visual_assessment import (
    OpenAIResponsesVisualAssessor,
    VisualComparisonRequest,
)


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-type", required=True, help="Event to assess visually.")
    parser.add_argument(
        "--isaac-frame",
        action="append",
        required=True,
        type=Path,
        help="Saved Isaac PNG/JPEG/WEBP frame; repeat in chronological order.",
    )
    parser.add_argument(
        "--world-model-frame",
        action="append",
        required=True,
        type=Path,
        help="Saved world-model PNG/JPEG/WEBP frame; repeat in chronological order.",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--detail", choices=("low", "high", "auto"), default="low")
    args = parser.parse_args()
    load_env(PROJECT_ROOT / ".env")
    model = (
        args.model
        or os.environ.get("VISUAL_ASSESSMENT_MODEL")
        or os.environ.get("RESEARCH_MODEL", "gpt-5.6-luna")
    )
    comparison = OpenAIResponsesVisualAssessor(model).assess(
        VisualComparisonRequest(
            args.event_type,
            tuple(args.isaac_frame),
            tuple(args.world_model_frame),
            args.detail,
        )
    )
    print(comparison.to_dict())


if __name__ == "__main__":
    main()
