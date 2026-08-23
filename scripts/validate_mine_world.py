#!/usr/bin/env python3
"""Validate the persistent mine_v1 USD asset inside Isaac Sim 6.0.1.

This is intentionally a validator and renderer, not a scene generator. Run it
with /isaac-sim/python.sh in the AWS container.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORLD_DIRECTORY = PROJECT_ROOT / "assets" / "worlds" / "mine_v1"
ENTRY_STAGE = WORLD_DIRECTORY / "mine_world.usda"

REQUIRED_PRIMS = (
    "/World", "/World/Environment", "/World/Environment/MineShell",
    "/World/Environment/Floor", "/World/Environment/Walls",
    "/World/Environment/Ceiling", "/World/Environment/StaticProps",
    "/World/FailureZones", "/World/FailureZones/Zone_RoofSupport",
    "/World/FailureZones/Zone_RoofSupport/BeamPrimary",
    "/World/FailureZones/Zone_RoofSupport/SupportPrimary",
    "/World/FailureZones/Zone_RoofSupport/InteractionTarget",
    "/World/FailureZones/Zone_Rockfall/Rock01",
    "/World/FailureZones/Zone_Rockfall/Rock02",
    "/World/FailureZones/Zone_Rockfall/RetainingObject",
    "/World/FailureZones/Zone_Debris/Debris01",
    "/World/FailureZones/Zone_Debris/Debris02",
    "/World/FailureZones/Zone_Debris/InteractionTarget", "/World/Robot",
    "/World/Sensors/ResearchCamera", "/World/Sensors/OverviewCamera", "/World/Lighting",
)
RIGID_BODIES = (
    "/World/FailureZones/Zone_RoofSupport/BeamPrimary",
    "/World/FailureZones/Zone_RoofSupport/SupportPrimary",
    "/World/FailureZones/Zone_Rockfall/Rock01",
    "/World/FailureZones/Zone_Rockfall/Rock02",
    "/World/FailureZones/Zone_Debris/Debris01",
    "/World/FailureZones/Zone_Debris/Debris02", "/World/Robot",
)
COLLIDERS = (
    "/World/Environment/Floor",
    "/World/FailureZones/Zone_RoofSupport/BeamPrimary/CollisionAndVisual",
    "/World/FailureZones/Zone_RoofSupport/SupportPrimary/CollisionAndVisual",
    "/World/FailureZones/Zone_Rockfall/Rock01/CollisionAndVisual",
    "/World/FailureZones/Zone_Rockfall/Rock02/CollisionAndVisual",
    "/World/FailureZones/Zone_Debris/Debris01/CollisionAndVisual",
    "/World/FailureZones/Zone_Debris/Debris02/CollisionAndVisual", "/World/Robot/Chassis",
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, default=ENTRY_STAGE)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument(
        "--skip-render",
        action="store_true",
        help="physics-only diagnostic for a host whose RTX shader pipeline is unavailable",
    )
    return parser.parse_args()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _validate_stage(stage: object) -> None:
    from pxr import UsdGeom, UsdPhysics

    for path in REQUIRED_PRIMS:
        _require(stage.GetPrimAtPath(path).IsValid(), f"missing required prim: {path}")
    for path in ("/World/Sensors/ResearchCamera", "/World/Sensors/OverviewCamera"):
        _require(stage.GetPrimAtPath(path).IsA(UsdGeom.Camera), f"not a camera: {path}")
    for path in RIGID_BODIES:
        _require(UsdPhysics.RigidBodyAPI.Get(stage, path), f"rigid-body API missing: {path}")
    for path in COLLIDERS:
        _require(UsdPhysics.CollisionAPI.Get(stage, path), f"collision API missing: {path}")
    _require(stage.GetPrimAtPath("/World/PhysicsScene").IsValid(), "missing PhysicsScene")


def _settle(world: object, frames: int, *, render: bool = True) -> None:
    for _ in range(frames):
        world.step(render=render)


def _save_rgba(image: object, output: Path) -> None:
    import numpy as np
    from PIL import Image

    pixels = np.asarray(image)
    _require(pixels.ndim == 3 and pixels.shape[2] >= 3, "camera returned no RGB image")
    if pixels.dtype != np.uint8:
        pixels = np.clip(pixels * 255 if pixels.max() <= 1 else pixels, 0, 255).astype(np.uint8)
    Image.fromarray(pixels[:, :, :3], mode="RGB").save(output)


def _render_cameras(world: object, paths: Iterable[str]) -> None:
    from isaacsim.sensors.camera import Camera

    outputs = (WORLD_DIRECTORY / "previews" / "research_camera.png", WORLD_DIRECTORY / "previews" / "overview_camera.png")
    for path, output in zip(paths, outputs, strict=True):
        camera = Camera(prim_path=path, resolution=(640, 360), frequency=30)
        camera.initialize()
        _settle(world, 3, render=True)
        _save_rgba(camera.get_rgba(), output)
        camera.destroy()


def _beam_z(prim: object) -> float:
    position, _ = prim.get_world_pose()
    return float(position[2])


def _roof_support_smoke_test(world: object, *, render: bool) -> None:
    """External pose perturbation only; gravity/contact provides the failure."""
    from isaacsim.core.prims import XFormPrim

    beam = XFormPrim("/World/FailureZones/Zone_RoofSupport/BeamPrimary")
    support = XFormPrim("/World/FailureZones/Zone_RoofSupport/SupportPrimary")
    before = _beam_z(beam)
    support.set_world_pose(position=(3.5, -2.2, 1.5))
    _settle(world, 120, render=render)
    after = _beam_z(beam)
    _require(after < before - 0.8, f"beam did not fall physically: z {before:.3f} -> {after:.3f}")
    print(f"roof-support smoke test: beam z {before:.3f} -> {after:.3f}")


def main() -> int:
    args = _args()
    stage_path = args.stage.resolve()
    _require(stage_path.is_file(), f"entry stage not found: {stage_path}")

    from isaacsim import SimulationApp

    app = SimulationApp(
        {
            "headless": True,
            "renderer": "None" if args.skip_render else "RayTracedLighting",
            # Keep the disposable validator from waiting for all RTX material
            # PSOs before the first sensor frame on cloud workstations.
            "/rtx/materialDb/syncLoads": False,
            "/rtx/hydra/materialSyncLoads": False,
            "/omni/kit/plugin/syncUsdLoads": False,
        }
    )
    import omni.usd
    from isaacsim.core.api import World

    try:
        context = omni.usd.get_context()
        _require(context.open_stage(str(stage_path)), f"failed to open stage: {stage_path}")
        for _ in range(300):
            app.update()
            if not context.get_stage_loading_status()[2]:
                break
        stage = context.get_stage()
        _require(stage is not None, "Isaac did not provide an opened stage")
        _validate_stage(stage)
        print(f"opened and validated: {stage_path}")
        world = World(stage_units_in_meters=1.0)
        world.reset()
        _settle(world, args.frames, render=not args.skip_render)
        if not args.skip_render:
            _render_cameras(world, ("/World/Sensors/ResearchCamera", "/World/Sensors/OverviewCamera"))
            print("rendered: previews/research_camera.png, previews/overview_camera.png")
        if args.smoke_test:
            _roof_support_smoke_test(world, render=not args.skip_render)
        return 0
    finally:
        # Isaac Sim 6.0.1 can abort when tearing down active camera task groups.
        # This disposable container validator exits after flushing its files,
        # matching the workstation handoff's verified shutdown strategy.
        pass


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as error:
        print(f"mine-world validation failed: {error}", file=sys.stderr)
        exit_code = 1
    finally:
        # The 6.0.1 image can abort in Kit camera task-group teardown. This is
        # a disposable validation container, so mirror the verified Phase 2
        # runner: flush artifacts and let process exit release Kit resources.
        sys.stdout.flush()
        sys.stderr.flush()
    os._exit(exit_code)
