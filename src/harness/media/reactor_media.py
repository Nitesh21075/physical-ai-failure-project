"""Normalize saved Reactor media without assigning it physical meaning."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


def normalize_reactor_media(
    run_directory: str | Path, evidence_refs: Iterable[str | Path] = (),
) -> dict[str, Any]:
    """Write a media manifest and thumbnail for an ordered saved-frame sequence.

    Reactor's native summary/event data is preserved as a referenced artifact.
    This function does not infer any pose, collision, world state, or event.
    """
    run_directory = Path(run_directory).resolve()
    refs = [Path(value) for value in evidence_refs]
    if not refs:
        refs = sorted((run_directory / "frames").glob("*"))
    media = [path for path in refs if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov"}]
    output = run_directory / "media" / "reactor"
    output.mkdir(parents=True, exist_ok=True)
    thumbnail: Path | None = None
    image = next((path for path in media if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}), None)
    if image:
        thumbnail = output / "thumbnail.png"
        try:
            with Image.open(image) as source:
                source.thumbnail((480, 270))
                source.save(thumbnail)
        except UnidentifiedImageError:
            thumbnail = None
    summary = run_directory / "summary.json"
    manifest = {
        "kind": "reactor_visual_evidence", "media_sequence": [str(path) for path in media],
        "thumbnail_path": str(thumbnail) if thumbnail else None,
        "native_metadata_path": str(summary) if summary.exists() else None,
        "timing_note": "Chunk positions are native Reactor sequence evidence; they are not synchronized to Isaac simulation time.",
    }
    manifest_path = output / "media.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest
