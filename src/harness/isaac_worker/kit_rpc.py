"""Typed dispatcher executed by NVIDIA's in-process Isaac Python Server.

The host sends only JSON arguments to this module.  It never submits model
generated Python source to the simulator.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harness.isaac_worker.server import IsaacExperimentRunner, IsaacWorker

_worker: IsaacWorker | None = None


def _get_worker() -> IsaacWorker:
    global _worker
    if _worker is None:
        import omni.kit.app

        runs_dir = Path(os.environ.get("ISAAC_RUNS_DIR", "/workspace/project/runs/isaac-worker"))
        _worker = IsaacWorker(
            runs_dir,
            IsaacExperimentRunner(
                runs_dir,
                application=omni.kit.app.get_app(),
                enable_camera=False,
            ),
            camera_available=False,
        )
    return _worker


def dispatch(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Handle one pre-defined harness RPC on Kit's own event loop."""
    return _get_worker().handle(method, path, payload)


async def run_experiment(
    compiled_experiment: dict[str, Any], campaign_id: str, iteration_id: str
) -> dict[str, Any]:
    """Run a compiler-produced experiment; the sole externally callable action."""
    return await _get_worker().run_async(
        {
            "request_id": f"{campaign_id}:{iteration_id}",
            "schema_version": "v1",
            "campaign_id": campaign_id,
            "iteration_id": iteration_id,
            "experiment": compiled_experiment,
        },
    )
