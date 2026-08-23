# Phase 3: Reactor Visual Adapter

Phase 3 adds `ReactorVisualEnvironment`, a backend-neutral wrapper for the
documented LingBot World 2 session model. It is intentionally visual-only:
each reset and action waits for a completed generated-video chunk, saves or
references that media through `Observation.sensor_refs`, and records only
session metadata in `Observation.state`.

## Adapter contract

- Backend name: `reactor/lingbot-world-2`.
- Required scenario parameters: `prompt` and a local `seed_image_path`.
- Optional scenario parameters: `chunk_timeout_seconds` and the fixed
  `model_name` value above.
- Supported action: `set_camera_controls`, containing documented navigation
  and look directions plus an optional `rotation_speed_degrees` in `[0, 30]`.
- The injected `ReactorSession` transport owns authentication, model
  connection, upload, streaming, frame persistence, timeouts, and teardown.

The adapter does **not** expose robot pose, contacts, object state,
`world_state`, or environmental-failure events. Those capabilities are not
available as authoritative structured output from the Reactor video session.
An image-based classifier, if later needed, must be a separate evaluator that
records confidence and media evidence rather than ground truth.

## Live validation handoff

Implement a `ReactorSession` transport only after model access is enabled for
`REACTOR_API_KEY`. Verify the currently enabled model identifier and SDK API,
then run a short session with a checked-in-safe local seed image supplied at
runtime. The transport must write received chunk/frame artifacts under the run
directory and return their paths as `ReactorVideoChunk.sensor_refs`.

This can be developed in WSL or on the AWS workstation because it is a remote
client. It does not require the Isaac container. Keep the validated Isaac
6.0.1 adapter separate; use the AWS GPU workstation only when exercising
Isaac/PhysX or comparing recorded artifacts across backends.
