# mine_v1: persistent mine failure-research world

`mine_world.usda` is the directly openable entry stage. It composes the static drift, materials, lighting, physics defaults, three hazard zones, and NVIDIA's articulated Nova Carter rover. Mine-authored references are relative; the selected rover reference is the documented NVIDIA Isaac 6.0 cloud asset URL, with a local proxy fallback variant.

## Layout

```text
mine_world.usda                 composed entry stage
mine_base.usda                  static mine shell and props
layers/                         physics, materials, lighting sublayers
hazards/                        individually referenced hazard assets
robots/inspection_robot.usda    Nova Carter reference + local proxy fallback variant
previews/                       rendered fixed-camera images
manifest.json                   stable prim registry for workers/tools
```

The installed Isaac Sim 6.0.1 image was inspected before authoring and does not include a local portable robot pack. The default robot is therefore a network-resolved NVIDIA Isaac 6.0 Nova Carter asset. It has PhysX articulation, wheels, cameras, IMUs, and lidars; its 3D-content-sharing license remains an external dependency. `/World/Robot` stays stable, and `robot_model=proxy_fallback` preserves an entirely local fallback if the asset root is unavailable.

## Physics model

Static scenery (`/World/Environment`) uses static collision geometry only. The beam, support, loose rocks, debris, and robot proxy are small independent rigid-body assemblies with collision geometry and explicit masses. This keeps the experiment count low and behavior inspectable.

The operational causal hazard is the roof-support zone:

```text
BeamPrimary (dynamic) rests on SupportPrimary (separate body)
  -> experiment moves SupportPrimary away
  -> contact support disappears
  -> PhysX gravity drops BeamPrimary
```

There is no timer, scripted collapse event, or scripted switch from kinematic to dynamic for `BeamPrimary`. The validation smoke test uses an external pose perturbation of the support, then verifies that PhysX has moved the beam down.

## Rover-caused failures

The default rover is NVIDIA Nova Carter: a real articulated wheeled robot, not
a fake event trigger. A future controller/VLA should command its wheel joints
and consume `/World/Robot/VLACamera` (plus any selected built-in Nova Carter
sensors). It must not teleport the chassis or invoke a `collapse` command.

- **Roof support:** approach the negative-Y side of
  `SupportPrimary/PushFace`, then drive in positive Y. The support is a
  distinct 22 kg body; moving it clear of the beam removes the only intended
  support and gravity causes the failure.
- **Rockfall:** approach the negative-Y side of
  `RetainingObject/PushFace`, then drive in positive Y. The dynamic retainer
  moves clear of the down-slope route, allowing the loose rocks to roll from
  the separate tilted ledge.
- **Debris:** drive the chassis into `Debris01` or `Debris02`; both are
  independent rigid bodies and require no special trigger.

These interaction recipes are registered in `manifest.json`. They are world
contracts for a future world-aware worker; the currently documented v1 Isaac
Worker remains intentionally limited to the original reference scene and does
not yet load or command this world. A future worker should map normal rover
movement commands to contact attempts and observe body poses/contact outcomes,
not expose an artificial `collapse` command.

## Validate in the AWS Isaac container

Run from the repository checkout that contains this world:

```bash
sudo docker run --rm --gpus all --network host --user 0:0 --entrypoint bash \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e HOME=/tmp \
  -v "$PWD:/workspace/project" \
  nvcr.io/nvidia/isaac-sim:6.0.1 \
  -lc 'cd /workspace/project && /isaac-sim/python.sh scripts/validate_mine_world.py --smoke-test'
```

The command opens the real composed stage, verifies the required paths and physics APIs, steps PhysX, renders both fixed cameras to `previews/`, and runs the bounded roof-support perturbation smoke test.

`previews/research_camera.png` and `previews/overview_camera.png` are temporary visual composition previews generated from the authored scene brief. They are not simulator frames: the current workstation image stalls in RTX PSO compilation even for the existing Phase 2 camera smoke scene. Replace them with the validator's camera output when that container condition is resolved; do not use the temporary research preview as a Reactor seed.

## Open interactively

Start Isaac Sim 6.0.1 with the project directory mounted at `/workspace/project` (the same mount as the validation command), then choose:

```text
File -> Open -> /workspace/project/assets/worlds/mine_v1/mine_world.usda
```

For an existing AWS container whose checkout is mounted at `/workspace/project`, the in-container path is the same. Do not put host `/home/ubuntu/...` paths in the USD.

## Experiment composition policy

Treat all files in this directory as immutable campaign inputs. A worker should load `mine_world.usda`, then author its changes in a stronger session or derived layer. Safe experiment operations are enumerated in `manifest.json`; they include moving `SupportPrimary`, setting its kinematic state for deterministic displacement, altering listed rigid-body properties, repositioning the robot, and adding an approved object. Do not flatten a composed experiment except when exporting a snapshot.
