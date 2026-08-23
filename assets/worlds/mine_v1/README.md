# mine_v1: persistent mine failure-research world

`mine_world.usda` is the directly openable entry stage. It composes the static drift, materials, lighting, physics defaults, three hazard zones, and a small self-contained wheeled inspection-robot proxy. All asset references are relative to this directory; the world has no Nucleus, `/Isaac`, or absolute host-path dependency.

## Layout

```text
mine_world.usda                 composed entry stage
mine_base.usda                  static mine shell and props
layers/                         physics, materials, lighting sublayers
hazards/                        individually referenced hazard assets
robots/inspection_robot.usda    reference-swappable robot proxy
previews/                       rendered fixed-camera images
manifest.json                   stable prim registry for workers/tools
```

The installed Isaac Sim 6.0.1 image was inspected before authoring. It does not include a portable built-in wheeled robot USD library, so v1 deliberately uses a repository-local proxy instead of embedding a brittle `/Isaac/...` or Nucleus path. `/World/Robot` stays stable and can later reference an approved robot USD without modifying the mine shell.

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
