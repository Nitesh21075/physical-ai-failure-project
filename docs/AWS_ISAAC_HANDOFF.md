# AWS Isaac Sim Handoff

## Purpose

This document records the workstation assumptions for the Phase 2 Isaac Sim
backend. Read it before changing Isaac-specific code or validating simulator work.

## Verified workstation baseline

- Host: AWS Ubuntu 24.04 GPU workstation.
- GPU: NVIDIA L40S with driver 595.58.03.
- Image: `nvcr.io/nvidia/isaac-sim:6.0.1`.
- Project checkout: `/home/ubuntu/physical-ai-failure-project` on the host.

## Running the Phase 2 smoke experiment

Run from the host checkout:

```bash
sudo docker run --rm --gpus all --network host --user 0:0 --entrypoint bash \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e HOME=/tmp \
  -v /home/ubuntu/physical-ai-failure-project:/workspace/project \
  nvcr.io/nvidia/isaac-sim:6.0.1 \
  -lc 'cd /workspace/project && /isaac-sim/python.sh scripts/run_isaac_phase2.py \
    --runs-dir /workspace/project/runs/isaac-phase2'
```

Why this form matters:

- `--entrypoint bash` prevents the image's streaming-app entrypoint from
  interpreting the Python command as streaming arguments.
- The image's normal user cannot write the host checkout. Running as root lets
  the mounted project receive artifacts; afterwards use
  `sudo chown -R ubuntu:ubuntu runs/isaac-phase2` if ownership matters.
- `ACCEPT_EULA` and `PRIVACY_CONSENT` are required for noninteractive startup.

The run writes ignored artifacts under `runs/`: scenario, trajectory, result,
and camera `.npy` frames. Do not commit generated runs or Isaac caches.

## Runtime constraints

- Keep Isaac imports inside the concrete runtime; the core orchestrator remains
  backend-neutral and is covered by ordinary host tests.
- The support beam must become kinematic only after `World.reset()`. PhysX
  rejects the default-velocity reset of an already-kinematic dynamic body.
- Isaac 6.0.1 can abort while tearing down active camera task groups. The
  disposable container runner flushes its artifacts and exits without Kit
  teardown; reusable applications need a separately verified shutdown path.
- Render every physics step when using this camera pipeline. In this image,
  non-rendered `World.step()` calls can stall camera/task processing.

## Development split

- Use WSL for schemas, orchestration, recorder/evaluator work, mocks, and
  non-Isaac backend clients. Run `.venv/bin/python -m pytest -q` there or here.
- Use this AWS workstation for Isaac/PhysX, GPU, camera, container, and any
  performance validation. Do not claim an Isaac change works from WSL alone.
- Phase 3 can begin in WSL if it is backend-neutral or a remote API client;
  bring it to AWS only when it needs this simulator or GPU validation.

## WebRTC streaming

WebRTC is valuable for manual scene inspection, debugging, and the demo. It is
not required for the deterministic headless smoke test, whose acceptance output
