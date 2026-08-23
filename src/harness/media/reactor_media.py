"""Normalize saved Reactor media without assigning it physical meaning."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


def _ffmpeg_executable() -> str:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise RuntimeError("Reactor video export requires ffmpeg or imageio-ffmpeg") from exc


def _export_frame_sequence(image_paths: list[Path], output: Path, fps: int = 5) -> Path | None:
    """Create a derived MP4 from saved Reactor frames without altering evidence."""
    frames_dir = output / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for stale_frame in frames_dir.glob("frame_*.png"):
        stale_frame.unlink()
    valid_frames = 0
    for path in image_paths:
        try:
            with Image.open(path) as image:
                image.convert("RGB").save(frames_dir / f"frame_{valid_frames:04d}.png")
        except UnidentifiedImageError:
            continue
        valid_frames += 1
    if not valid_frames:
        return None
    video_path = output / "replay.mp4"
    try:
        subprocess.run(
            [
                _ffmpeg_executable(), "-y", "-framerate", str(fps),
                "-i", str(frames_dir / "frame_%04d.png"),
                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(video_path),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return video_path


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
    media = [
        path for path in refs
        if path.exists()
        and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov"}
    ]
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
    image_frames = [
        path for path in media if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    derived_video = _export_frame_sequence(image_frames, output) if image_frames else None
    summary = run_directory / "summary.json"
    native_metadata: dict[str, Any] | None = None
    if summary.exists():
        try:
            decoded = json.loads(summary.read_text(encoding="utf-8"))
            native_metadata = decoded if isinstance(decoded, dict) else None
        except json.JSONDecodeError:
            # Preserve the native file reference even if a partial session log
            # cannot be parsed.  It is evidence, not a harness-owned schema.
            native_metadata = None
    # Keep timing/chunk data only when the native session log actually exposed
    # it.  Do not infer timestamps or physical events from generated pixels.
    chunk_metadata = None
    if native_metadata:
        chunk_metadata = next(
            (native_metadata[key] for key in ("chunks", "chunk_metadata", "chunk_timing") if key in native_metadata),
            None,
        )
    playable_video = next(
        (str(path) for path in media if path.suffix.lower() in {".mp4", ".webm", ".mov"}),
        str(derived_video) if derived_video else None,
    )
    manifest = {
        "kind": "reactor_visual_evidence",
        "playable_video_path": playable_video,
        "derived_video_path": str(derived_video) if derived_video else None,
        "media_sequence": [
            {"position": position, "path": str(path)} for position, path in enumerate(media)
        ],
        "thumbnail_path": str(thumbnail) if thumbnail else None,
        "native_metadata_path": str(summary) if summary.exists() else None,
        "chunk_metadata": chunk_metadata,
        "timing_note": "Chunk positions are native Reactor sequence evidence; they are not synchronized to Isaac simulation time.",
    }
    manifest_path = output / "media.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest
