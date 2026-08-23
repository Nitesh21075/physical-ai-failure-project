# Backend Integration Boundaries

This document defines the intended roles of Alakazam Studio, Reactor, and
Isaac Sim without changing the Phase 0/1 backend-neutral architecture.

The harness environment contract is the existing synchronous interface:

```python
class Environment:
    @property
    def backend_name(self) -> str: ...

    def reset(self, scenario: Scenario) -> Observation: ...
    def step(self, action: Action) -> StepResult: ...
    def observe(self) -> Observation: ...
    def close(self) -> None: ...
```

`Observation.state` is optional structured state.  A backend that supplies
only video must record that video through `sensor_refs`; it must not claim that
it has authoritative physical state.

## Capability terms

- **Satisfies**: the backend can implement the harness method as its normal
  runtime operation.
- **Conditional**: the method can be wrapped, but only with the stated
  restrictions; it is not a general robot-simulation implementation.
- **Does not satisfy**: do not implement this backend as an `Environment` on
  the basis of its currently documented capability.

## Isaac Sim / PhysX

**Intended role:** the first full environment backend and the Phase 2 target.
It is the physics-grounded reference for Plan B and, later, one half of Plan C.

### Interface coverage

- `backend_name`: **satisfies** as `"isaac_sim"`.
- `reset(scenario)`: **satisfies** by loading/resetting the selected USD scene,
  robot, hazard configuration, and random seed.
- `step(action)`: **satisfies** by translating the chosen controller action,
  advancing a fixed number of physics frames, and collecting resulting events.
- `observe()`: **satisfies** with simulation time, robot/scene state, contact
  or hazard events, and camera/sensor artifact references.
- `close()`: **satisfies** by releasing the Isaac application/runtime and
  any render or sensor resources.

NVIDIA documents simulation reset, manual stepping, world loading, entity
state inspection, and sensor/robot workflows. The exact APIs and supported
asset formats must be selected from the installed AWS container version, not
hard-coded from web examples.

### Phase 2 adapter design

Implement only `harness/environments/isaac_sim.py`, imported exclusively when
executed inside the AWS Isaac Sim container. The core orchestrator, schemas,
recorder, evaluator, and mock backend remain unchanged.

`IsaacSimEnvironment` will own the simulator lifecycle and provide these
translations:

1. **Scenario to reset plan.** Validate `scenario.environment == "isaac_sim"`.
   Convert the v0 allow-listed parameters and hazards into scene, robot,
   initial-pose, target, and deterministic-hazard settings. Reject unsupported
   keys rather than generating simulator code from prompt text.
2. **Action to controller command.** The v0 reference scene accepts only
   `set_planar_velocity` actions with numeric `x` and `y` values. It drives a
   rigid-body mobile robot proxy; `IsaacPlanarVelocityController` supplies the
   reference controller. A future articulated-robot adapter can add a separate,
   documented vocabulary without changing the orchestrator.
3. **Simulation to `StepResult`.** Advance a fixed, recorded number of physics
   frames. Return the post-step `Observation`, a copied structured world-state
   subset, domain events (contacts, hazard activation, and terminal state), and
   `done`.
4. **Sensors to artifacts.** Save camera frames/video outside Git under the run
   directory and put only their paths in `sensor_refs`. Keep small numeric
   robot/scene state in `Observation.state` and `StepResult.world_state`.
5. **Hazard evaluation input.** Emit an explicit environmental event when the
   deterministic hazard triggers; the existing evaluator can then distinguish
   environmental failure from task completion.

Phase 2 acceptance criteria are therefore: one rigid-body robot proxy, one
simple scene, one allow-listed controller vocabulary, one deterministic
environmental hazard, and a headless AWS-container test run that produces a
normal recorded harness experiment.

The container-only smoke run is:

```text
./python.sh scripts/run_isaac_phase2.py --runs-dir /workspace/runs
```

It runs the standard orchestrator with `IsaacPlanarVelocityController` and
writes the normal scenario, trajectory, result, and camera artifacts.

### Remaining Isaac Sim decisions and gaps

- The local development machine has no Isaac installation. The adapter follows
  the documented Isaac Sim 5.x standalone APIs and must be run/validated with
  the AWS container's `python.sh` before relying on it.
- The v0 scene uses a rigid-body mobile robot proxy. A production robot asset
  and articulated controller remain a follow-on adapter decision.
- Camera configuration, contact-event extraction, and hazard implementation
  are backend work; none should leak into `Orchestrator`.
- This backend requires the AWS GPU workstation/container. Local unit tests
  continue to use `MockEnvironment`.

## Reactor

**Intended role:** a future neural-world *visual* backend, only if the granted
model and credentials support a meaningful closed-loop interaction. It is not
a Phase 2 dependency.

The current Reactor documentation for LingBot World 2 describes a session
which starts from both a prompt and a reference image, streams video in chunks,
and accepts prompt/camera-steering commands. Command effects occur at the next
chunk boundary and errors are delivered asynchronously.

### Interface coverage

- `backend_name`: **conditional** as a model-qualified value such as
  `"reactor/<model-name>"`; the model name and SDK version must be recorded.
- `reset(scenario)`: **conditional**. A Reactor session can be reset, seeded,
  given a prompt and reference image, then started. This is session setup, not
  a physics-world reset, and requires the model's required conditioning inputs.
- `step(action)`: **conditional and narrow**. A wrapper may translate only the
  model's documented steering controls (for example movement/look or a prompt
  update), wait for a completed chunk, and return one visual step. It does not
  implement arbitrary robot joint, end-effector, force, or contact actions.
- `observe()`: **conditional**. It can expose a captured video frame/chunk via
  `sensor_refs` plus non-physical session metadata. It does not currently
  provide authoritative robot pose, object state, contacts, collision state,
  or environmental-failure events.
- `close()`: **unconfirmed** for the selected SDK/model. Treat connection
  teardown as a required adapter capability to verify before implementation;
  do not assume a method name.

### Capability gaps

- Reactor output is generative video, not structured physical state. It cannot
  directly support physics-grounded collapse, fire, debris, or contact labels.
- Documented steering is camera/navigation control, not a general robot-control
  interface. A robot-policy experiment needs a model-specific action mapping
  and must label it as visual steering.
- Stepping is asynchronous and chunk-based, whereas the Phase 0/1 environment
  interface is synchronous. A future wrapper may block for a chunk boundary,
  but must retain the chunk index and latency in trajectory metadata.
- A seed controls initial noise for the documented model; this alone is not a
  determinism or reproducible-physics guarantee.
- Credentials and the exact model capability remain prerequisites. If they do
  not expose suitable closed-loop controls, use Reactor only for visual
  counterfactual/augmentation artifacts, not as an `Environment`.

### Future adapter boundary

If capability validation succeeds, implement a separate
`ReactorVisualEnvironment` after Phase 2. It should use a model-specific client
behind a small transport adapter, save sampled frames/chunks as media artifacts,
and populate only truthful session metadata in state. It must not modify the
orchestrator or fabricate environmental events from unverified pixels. Any
visual event classifier belongs in a separate evaluator/annotation layer with
its confidence and evidence references recorded.

## Alakazam Studio

**Intended role:** scenario authoring, state-graph editing/versioning, and
human visual review—not the Phase 2 simulation backend.

Alakazam Studio is a browser-based state-machine editor/player. It can use a
Reactor, hosted Alakazam, or custom WebSocket provider to render a world, but
the Studio repository contains neither model weights nor a physics runtime.
Its offline mock exercises authored graph transitions but is explicitly a
canvas stub rather than a renderer.

### Interface coverage

- `backend_name`: **does not satisfy**. Studio is not a harness environment.
- `reset(scenario)`: **does not satisfy** as a direct harness operation. Studio
  has its own world/session concepts, but no documented Python environment API
  for resetting a robot simulation from `Scenario`.
- `step(action)`: **does not satisfy**. Studio transitions authored events in a
  semantic state graph; it does not execute robot-control actions or physics.
- `observe()`: **does not satisfy** for harness state. It may display graph and
  provider output, but it is not an authoritative source of robot/world state.
- `close()`: **does not satisfy** as a backend lifecycle operation.

### Intended integration boundary

Use a future `AlakazamScenarioBridge`, not an `Environment` subclass. The
bridge may import/export a versioned Studio world or selected state/event graph
into an allow-listed harness `Scenario`, preserving Studio world/version IDs as
provenance. It may also link a recorded harness run to a Studio view for human
review.

The mapping is intentionally one-way in authority:

```text
Studio state graph / authored event
            -> reviewed scenario parameters and hazards
            -> harness Environment (Isaac Sim or qualified neural backend)
            -> recorded trajectory and evaluation
            -> optional Studio review link
```

Studio's `promptableEvents` capability is relevant only to whether its selected
renderer receives authored graph events. It does not establish that the
renderer accepts robot actions, exposes structured state, or simulates physical
consequences.

### Capability gaps

- No physics engine, robot model, contact data, or environmental-failure ground
  truth.
- No documented headless Python `Environment` API.
- Provider video/state is provider-specific and must be assessed separately;
  choosing Reactor inside Studio does not upgrade Reactor's capabilities.
- Browser-local credential storage is unsuitable for an unattended harness;
  any server-side bridge must keep secrets outside source control and outside a
  browser bundle.

## Evidence to re-check at implementation time

- [Alakazam Studio README](https://github.com/Alakazam-studios/alakazam-studio):
  provider roles, state-graph behavior, custom WebSocket support, and the
  `promptableEvents` capability probe.
- [Reactor LingBot World 2 API](https://www.reactor.inc/models/lingbot-world-2/api):
  session prerequisites, chunk/event semantics, commands, and exposed video
  track. Verify the exact hackathon-enabled model instead of assuming LingBot
  represents every Reactor model.
- [NVIDIA Isaac Sim simulation interfaces](https://docs.nvidia.com/learning/physical-ai/going-further-with-robotics/latest/scalable-multi-robot-scene-workflows-using-ros-simulation-interfaces-standard-in-isaac-sim/06-simulation-interfaces.html):
  reset, stepping, world/entity state, and version-specific deployment details.

These sources describe product capabilities, not a commitment that the local
credentials, installed versions, assets, or selected models expose every listed
feature. Verify those facts on the AWS workstation before writing an adapter.
