"""Launch the long-lived localhost Isaac worker inside the Isaac container."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from harness.isaac_worker import IsaacWorker, serve
from harness.isaac_worker.server import IsaacExperimentRunner


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("/workspace/project/runs/isaac-worker"))
    parser.add_argument("--port", type=int, default=8211)
    parser.add_argument(
        "--disable-camera",
        action="store_true",
        help="Run physics-only while the installed legacy camera path is unavailable.",
    )
    args = parser.parse_args()
    # SimulationApp is constructed before accepting requests, and worker calls
    # remain serialized to one simulator process.
    worker = IsaacWorker(
        args.runs_dir,
        IsaacExperimentRunner(args.runs_dir, enable_camera=not args.disable_camera),
        camera_available=not args.disable_camera,
    )
    try:
        serve(worker, port=args.port)
    finally:
        worker.close()


if __name__ == "__main__":
    main()
