# Intelligent Physical-AI Research Harness — AWS Implementation Instructions

## Purpose

Implement the next milestone of `Nitesh21075/physical-ai-failure-project`: an **intelligent, persistent research harness** that uses the **OpenAI Responses API** as the runtime research model, while keeping Isaac Sim/PhysX inside its existing NVIDIA container on the AWS workstation.

This milestone turns the current system from:

```text
human/Codex chooses scenario
        ->
harness executes experiment
        ->
Isaac/Reactor artifacts + Plan C comparison
```

into:

```text
research objective
        ->
Responses API Research Agent
        ->
hypothesis + constrained experiment/world-edit plan
        ->
host-side harness validates and compiles it
        ->
Isaac worker in container + Reactor backend
        ->
record/evaluate/compare
        ->
persistent research memory/state
        ->
next research iteration
```

The current repository, existing tests, working Isaac path, Reactor integration, Plan C semantics, persistence layer, media handling, and current dashboard must be inspected before implementation.

Do **not** assume this document is more accurate than the code where they conflict. Preserve already-working interfaces unless there is a concrete need to extend them.

---

# 1. Read the current repository first

Before editing, inspect at least:

```text
AGENTS.md
README.md

docs/PROJECT.md
docs/ARCHITECTURE.md
docs/BACKENDS.md
docs/PLAN_C.md
docs/AWS_ISAAC_HANDOFF.md
docs/EXPERIMENT_PERSISTENCE_DASHBOARD.md
docs/REACTOR_HANDOFF.md

src/harness/schemas.py
src/harness/orchestration/
src/harness/environments/
src/harness/agents/
src/harness/evaluation/
src/harness/recording/
src/harness/comparison/
src/harness/persistence/
src/harness/dashboard/

scripts/
tests/
pyproject.toml
```

Run the existing unit tests before changing architecture and record the baseline.

The current design principles remain binding:

- filesystem run artifacts are authoritative;
- SQLite is a reconstructable metadata/research index, not a blob store;
- Isaac is a physics-grounded simulated reference;
- Reactor is neural-world visual evidence and must not be presented as authoritative physical state;
- Plan C may use semantic action alignment when exact replay is impossible;
- Codex CLI is a development tool, not the normal runtime researcher;
- generated trajectories/media/caches stay out of Git;
- API keys never enter source control.

---

# 2. Deployment topology — this is critical

The intelligent harness runs on the **AWS Ubuntu workstation host**.

Isaac Sim runs in the existing NVIDIA container, currently based on:

```text
nvcr.io/nvidia/isaac-sim:6.0.1
```

Therefore host-side Python must **not import Isaac Sim modules**.

The topology must be:

```text
AWS HOST
========================================================================

Research campaign service
    |
    +-- OpenAI Responses API client
    |
    +-- persistent campaign/research memory (SQLite)
    |
    +-- scenario/world-plan validator
    |
    +-- Plan C coordinator
    |
    +-- Reactor client/backend
    |
    +-- dashboard/API
    |
    +-- IsaacClient
            |
            | localhost IPC / RPC
            v

----------------------- container boundary -----------------------------

ISAAC SIM CONTAINER
========================================================================

Long-lived IsaacWorker
    |
    +-- SimulationApp / Kit
    +-- USD / Omniverse / Isaac APIs
    +-- scene/world authoring
    +-- assets
    +-- physics
    +-- camera/sensors
    +-- experiment execution
    +-- state/event capture
    +-- stage/replay artifact writing

========================================================================
```

Do **not** solve this by trying to install/import Isaac Sim into the host `.venv`.

Do **not** make the Responses API execute Docker commands directly.

The host application owns research policy. The Isaac container owns simulator-native operations.

---

# 3. Build a long-lived host <-> Isaac container bridge

The current one-shot Phase 2 runner is useful for validation but is not the correct runtime architecture for repeated autonomous experiments.

Implement a stable bridge with two layers:

```text
host:
    IsaacClient

container:
    IsaacWorker / IsaacRPCServer
```

Prefer a small localhost JSON RPC/HTTP protocol because it is transparent and easy to debug.

A reasonable initial deployment is:

```text
docker --network host
IsaacWorker binds only to 127.0.0.1:<private_port>
```

The server must not be exposed publicly.

If the installed container/runtime makes a local HTTP server awkward, a mounted Unix socket is acceptable. Do not add complex distributed infrastructure.

The important property is:

**one long-lived Isaac/Kit process can execute multiple reset/run experiments without starting a new container for every research iteration.**

Suggested endpoint/capability surface:

```text
GET  /health
GET  /capabilities

POST /session/reset
POST /world/compile
POST /world/apply
POST /experiment/run
GET  /experiment/status/<id>
GET  /experiment/result/<id>
POST /stage/save

POST /session/close       # for controlled shutdown only
```

Exact route names may differ, but keep the protocol narrow and typed.

Every RPC must have:

- request ID;
- campaign/run ID where relevant;
- schema version;
- explicit success/error response;
- bounded timeouts;
- no arbitrary Python/code execution field.

The host must be able to detect:

- worker unavailable;
- Isaac startup failure;
- invalid world plan;
- missing asset;
- unsupported capability;
- run timeout;
- simulator exception;
- camera/sensor failure.

Do not silently retry destructive/ambiguous operations.

---

# 4. Responses API is the runtime research model

Use the **OpenAI Responses API** for the research intelligence.

Do not shell out to Codex CLI.

Do not use Codex SDK for ordinary campaign execution in this milestone.

Create a provider abstraction such as:

```python
class ResearchModel(Protocol):
    def propose_next_experiment(
        self,
        request: ResearchRequest,
    ) -> ResearchProposal:
        ...
```

First implementation:

```text
OpenAIResponsesResearchModel
```

Configuration via environment/config, e.g.:

```text
OPENAI_API_KEY=
RESEARCH_MODEL_PROVIDER=openai
RESEARCH_MODEL=<configurable model id>
```

Do not hard-code secrets.

Use official current OpenAI SDK/Responses API patterns.

Use Structured Outputs / strict function schemas where appropriate so experiment plans are machine validated.

The model must not return arbitrary executable Python as its experiment representation.

---

# 5. Agent memory and state are first-class requirements

There are **two distinct kinds of state**. Implement both.

## 5.1 Durable research memory — authoritative

The primary memory is local persistent campaign state in SQLite.

It must survive:

- Python process restart;
- dashboard restart;
- SSH disconnect;
- OpenAI response-chain loss;
- Isaac worker restart.

Persist at least:

```text
research_campaigns
research_iterations
research_hypotheses
research_proposals
operator_instructions
campaign_events
```

Each campaign should contain:

```text
campaign_id
objective
constraints
status
experiment_budget
experiments_used
created_at
updated_at
current_iteration
model_provider
model_name

openai_conversation_id OR response-chain metadata
last_openai_response_id

active/known parameter-space version
simulator implementation/version metadata
```

Each iteration should retain:

```text
iteration_id
campaign_id
ordinal
input context summary
hypothesis
rationale_summary
proposal JSON
validation result
compiled experiment reference
Isaac run ID
Reactor run ID
Plan C pair ID
comparison status
human review state
iteration state
failure/error information
timestamps
OpenAI response ID
```

Do not store hidden chain-of-thought.

Store only concise, model-authored rationale/hypothesis intended for the research record.

## 5.2 Responses API conversation continuity — supplementary

Use Responses API state support for continuity between research turns.

Either:

```text
conversation = one OpenAI conversation per research campaign
```

or a persisted:

```text
previous_response_id chain
```

depending on the current SDK/API pattern selected during implementation.

Persist the relevant OpenAI conversation/response identifiers in SQLite.

Important:

**Do not rely on the OpenAI conversation alone as experiment memory.**

Each research turn must still receive a compact, explicit research context built from our database, including the objective, current constraints, budget, important past outcomes, reviewed discrepancies, tested parameter regions, and operator instructions.

This gives us:

```text
Responses conversation state
    = conversational continuity

SQLite research state
    = authoritative scientific memory
```

If the OpenAI conversation chain is unavailable, the campaign should be reconstructable from SQLite and continue with a fresh model conversation after operator confirmation or an explicit recovery path.

---

# 6. Research-agent role

The Research Agent is an **experiment-level researcher**.

It should:

- inspect compact prior results;
- form a testable hypothesis;
- decide what information is missing;
- propose the next controlled experiment;
- optionally request approved world-authoring operations;
- explain a concise operator-facing rationale;
- learn from evaluated results and human review;
- avoid repeating equivalent experiments without a reason;
- respect budget and constraints.

It must **not**:

- edit repository source code during a campaign;
- invoke Codex CLI;
- modify evaluator definitions;
- change comparison thresholds opportunistically;
- modify the physics engine;
- execute arbitrary shell commands;
- directly operate Docker;
- fabricate Isaac results;
- fabricate Reactor structured physical state;
- run an unbounded loop.

The LLM operates at the **experiment timescale**, not the physics-control timescale.

Keep robot control inside deterministic/policy/controller components.

---

# 7. Research request and proposal schemas

Create strongly validated schemas, ideally under:

```text
src/harness/research/
```

Suggested files:

```text
src/harness/research/__init__.py
src/harness/research/schemas.py
src/harness/research/model.py
src/harness/research/openai_responses.py
src/harness/research/context.py
src/harness/research/agent.py
src/harness/research/campaign.py
src/harness/research/compiler.py
src/harness/research/search_space.py
src/harness/research/events.py
```

Suggested logical schemas:

```text
ResearchObjective
ResearchConstraint
ResearchBudget
ResearchContext
ResearchHypothesis
ExperimentIntent
WorldEditPlan
ExperimentProposal
CompiledExperiment
ResearchIteration
ResearchCampaign
CampaignEvent
```

A proposal should resemble:

```json
{
  "hypothesis": "The neural world may remain visually stable near the physical support-loss boundary.",
  "rationale_summary": "Recent reviewed trials suggest the disagreement begins close to marginal support.",
  "focus": "failure_boundary",
  "experiment_intent": {
    "task": "reach_target_without_causing_structural_collapse",
    "seed": 18273
  },
  "parameter_changes": {
    "robot_speed_mps": 0.85,
    "support_offset_m": 0.045
  },
  "world_edits": [],
  "expected_information_gain": "high"
}
```

The exact fields must reflect capabilities that actually exist.

Do not expose fictional parameters merely to make the example work.

---

# 8. Search-space and capability registry

The model must know what it is actually allowed to change.

Build an explicit capability/search-space layer.

Example conceptual interface:

```python
@dataclass(frozen=True)
class ParameterSpec:
    name: str
    kind: Literal["float", "int", "enum", "bool"]
    minimum: float | None
    maximum: float | None
    allowed_values: tuple[str, ...]
    description: str
    backend_scope: str
```

And:

```python
class WorldCapabilities:
    supported_parameters: ...
    supported_world_operations: ...
    available_asset_categories: ...
    supported_actions: ...
    supported_sensors: ...
```

The `ResearchContext` sent to the model must include only capabilities verified by the current harness/Isaac worker.

Any proposal outside the declared capability set must fail validation before simulator execution.

---

# 9. World authoring — allow experiment changes, not source-code changes

We do want the intelligent harness to eventually create richer experiment worlds.

Do this through **approved typed world-authoring operations**, not through arbitrary generated code.

Create a backend-neutral world-edit schema such as:

```text
SpawnPrimitive
SpawnAsset
RemoveObject
SetPose
SetRigidBodyProperties
SetMaterialProperties
SetCollisionProperties
AddFixedJoint
AddRevoluteJoint
ConfigureCamera
ConfigureSensor
SaveStage
```

Only implement operations that can be verified against the installed Isaac/Omniverse APIs.

The initial set can be small.

A possible `WorldEditPlan`:

```json
{
  "operations": [
    {
      "op": "set_pose",
      "object_id": "support_1",
      "position": [1.8, 0.0, 1.2]
    },
    {
      "op": "set_rigid_body_properties",
      "object_id": "robot_proxy",
      "mass_kg": 7.5
    }
  ]
}
```

No field may contain arbitrary Python.

The host:

```text
ResearchProposal
    ->
validate WorldEditPlan
    ->
ScenarioCompiler
    ->
IsaacClient
```

The container:

```text
IsaacWorker
    ->
translate typed operations
    ->
USD / Isaac / Omniverse APIs
```

This is how the Responses model changes Isaac experiment state without needing Codex SDK.

---

# 10. Asset spawning

Add an explicit asset catalog/discovery boundary.

Do not let the model crawl arbitrary filesystem paths itself.

Conceptual tools:

```text
list_asset_categories()
search_assets(query, category=None, limit=...)
inspect_asset(asset_id)
```

Return safe metadata:

```text
asset_id
display_name
source
USD path/reference known to Isaac
semantic category
optional dimensions/bounds if discoverable
compatibility notes
```

Then allow:

```text
spawn_asset(asset_id, prim_path, pose, ...)
```

The asset catalog can initially be a curated manifest discovered from assets verified on this AWS Isaac installation.

Do not block the milestone on building a huge asset index.

The system must gracefully return:

```text
CAPABILITY_MISSING
ASSET_NOT_AVAILABLE
```

rather than generating code.

---

# 11. ScenarioCompiler is a mandatory boundary

Implement a compiler between agent intent and backend-native execution:

```python
class ScenarioCompiler(Protocol):
    def compile(
        self,
        proposal: ExperimentProposal,
        capabilities: WorldCapabilities,
    ) -> CompiledExperiment:
        ...
```

`CompiledExperiment` should preserve:

- research hypothesis reference;
- semantic task/intent;
- seed;
- allowed parameter values;
- world edits;
- backend-specific Isaac scenario;
- backend-specific Reactor scenario where possible;
- action-alignment declaration;
- provenance.

This compiler is where we enforce the distinction:

```text
semantic experiment
    !=
Isaac-native representation
    !=
Reactor-native representation
```

Do not make the Research Agent emit raw Isaac Python or raw Reactor transport calls.

---

# 12. Plan C integration

Reuse the existing `MatchedExperimentSpec`, comparator, and paired-record semantics.

Research loop:

```text
ResearchAgent
      |
      v
ExperimentProposal
      |
      v
ScenarioCompiler
      |
      +------> Isaac scenario / world plan
      |
      +------> Reactor scenario
      |
      v
MatchedExperimentSpec
      |
      v
existing Plan C execution + comparator
```

Preserve:

- exact / semantic / unavailable action alignment;
- explicit alignment notes;
- Isaac as simulated physics evidence;
- Reactor as neural-world visual evidence;
- `candidate_discrepancy` wording rather than claiming the neural model is conclusively wrong;
- `inconclusive` when visual assessment is absent/weak.

If Reactor visual assessment is still manual, the campaign must support:

```text
WAITING_FOR_ASSESSMENT
```

Do not fake automatic assessment.

Design a future `VisualAssessor` interface but do not implement a VLM assessor unless explicitly requested after this milestone.

---

# 13. Campaign state machine

Implement explicit campaign/iteration states.

Campaign states:

```text
CREATED
RUNNING
PAUSED
STOPPING
STOPPED
COMPLETED
FAILED
```

Iteration states should include:

```text
BUILDING_CONTEXT
THINKING
PROPOSAL_RECEIVED
VALIDATING
COMPILED
RUNNING_ISAAC
RUNNING_REACTOR
WAITING_FOR_ASSESSMENT
COMPARING
RECORDED
FAILED
```

Persist every transition as a campaign event.

The state machine must be recoverable after process restart.

On startup, a campaign left in a nonterminal execution state must not blindly re-run a possibly already-executed physical experiment. Reconcile recorded artifacts/run IDs first and require idempotent recovery logic.

---

# 14. Budget, retries, and autonomy bounds

A research campaign must have explicit limits.

At minimum:

```text
max_experiments
max_invalid_proposals_per_iteration
max_model_retries
max_simulation_retries
max_wall_clock_per_experiment
```

Do not implement an infinite while-loop.

If budget is exhausted:

```text
COMPLETED
```

If the model repeatedly emits invalid proposals:

```text
PAUSED or FAILED
```

with a useful reason.

If a required capability is unavailable:

```text
PAUSED_CAPABILITY_REQUIRED
```

or equivalent persisted condition.

This is a point where a human may later ask Codex CLI to add a new simulator capability.

---

# 15. Research context construction

Build a compact context from persisted data.

Do not send every trajectory/video every iteration.

A useful research context includes:

```text
objective
campaign constraints
budget remaining

current world/simulator capability summary

recent experiments
highest-severity failures
highest-confidence candidate discrepancies
human-reviewed valid discrepancies
human-reviewed bad generations/simulator artifacts
tested parameter configurations

boundary-relevant neighboring experiments

operator instructions since last iteration
```

Prefer structured summaries.

Include artifact references only when useful.

Later we may add selected images/video frames, but do not make full media-history transmission mandatory for v0.

---

# 16. Research scoring / selection support

Do not make the LLM the only source of memory/search logic.

Add simple deterministic helper metrics where possible.

Useful future/current concepts:

```text
novelty
duplicate/near-duplicate detection
failure severity
comparison status
human review priority
distance to known failure boundary
parameter-space coverage
```

For v0, implement at least duplicate/near-duplicate protection for the parameters genuinely available.

The agent should be warned if it proposes an already-tested experiment and asked for a reason or a different proposal.

---

# 17. Operator instructions and interaction

The runtime harness must support operator steering.

An operator instruction is not arbitrary shell input.

Examples:

```text
"Explore closer to the last reviewed discrepancy."
"Focus on lower velocities."
"Avoid experiments already marked bad world-model generation."
"Pause after the next valid pair."
```

Persist instructions with timestamp and campaign ID.

The next model request receives pending instructions.

Mark them consumed/acknowledged in research state after incorporation, but keep the historical record.

The dashboard changes for this milestone should be minimal. The current redesigned GUI should not be replaced.

Only add backend/API support necessary to expose:

```text
campaign status
current iteration
current hypothesis
rationale summary
proposal
execution stage
budget
operator instructions
pause/resume/stop
```

Do not perform another broad dashboard redesign.

---

# 18. Research events for GUI observability

Emit/store clean application events, independent of presentation:

```text
campaign_created
campaign_started
context_built
model_request_started
model_response_received
proposal_validated
proposal_rejected
experiment_compiled
isaac_started
isaac_completed
reactor_started
reactor_completed
assessment_required
comparison_completed
iteration_recorded
campaign_paused
campaign_resumed
campaign_completed
campaign_failed
```

Each event should have:

```text
event_id
campaign_id
iteration_id if relevant
timestamp
event_type
small structured payload
```

Do not expose hidden model reasoning.

The GUI can later render these however desired.

---

# 19. Container-side IsaacWorker responsibilities

Implement simulator-specific logic in a container-side module, e.g.:

```text
src/harness/isaac_worker/
    server.py
    runtime.py
    capabilities.py
    world_authoring.py
    assets.py
    schemas.py
```

or another clear location.

Important: host imports of normal harness packages must still work without Isaac installed.

Only the worker/runtime process imports:

```text
isaacsim
omni.*
pxr.*
```

The worker should initialize `SimulationApp` once.

It should be able to:

1. report its actual installed version/capabilities;
2. create/reset a stage;
3. load a base scene where supported;
4. apply validated world operations;
5. configure the current experiment;
6. run bounded physics;
7. record structured state/events;
8. capture media;
9. save a stage snapshot for selected runs if requested;
10. return artifact references/result metadata to the host.

Do not claim an API works until it is tested inside the actual `6.0.1` container.

---

# 20. Host-side IsaacClient responsibilities

Implement a host-side client that has zero Isaac imports.

It should:

- check worker health/version;
- request capabilities;
- submit compiled experiments/world plans;
- poll or await bounded completion;
- translate worker result metadata into existing harness `Observation`/`ExperimentRecord`/artifact structures where appropriate;
- persist worker/container/version provenance.

Do not bypass the existing recorder/persistence model unless required.

---

# 21. Provenance and reproducibility

For every research iteration involving Isaac, persist enough provenance to know what laboratory executed it.

Record where available:

```text
repository git SHA
Isaac container image/tag
container image digest if practical
Isaac version
worker protocol/schema version
base scene ID/hash
asset manifest IDs/hashes
scenario seed
world edit plan
compiled scenario
model provider/model
research campaign/iteration ID
```

The research model must not change repository source during an active campaign.

If source code changes, the next campaign/experiment must record the new git SHA.

---

# 22. Testing strategy

All existing tests must remain green.

Add backend-independent tests for:

### Research model and schemas
- valid proposal parsing;
- Structured Output mapping;
- invalid/missing fields;
- prohibited arbitrary-code fields;
- fake model behavior.

### Memory/state
- campaign persistence;
- iteration persistence;
- response/conversation ID persistence;
- restart/recovery;
- operator instruction persistence;
- campaign status transitions.

### Context
- compact context construction;
- budget inclusion;
- reviewed discrepancy inclusion;
- duplicate experiment detection;
- tested-parameter summarization.

### Compiler
- proposal -> compiled experiment;
- unsupported parameter rejection;
- unsupported world operation rejection;
- action alignment generation;
- provenance retention.

### Isaac bridge
Use a fake worker/client locally.

Test:
- health;
- capability negotiation;
- experiment submission;
- worker error mapping;
- timeout handling;
- missing capability;
- idempotent run identifiers.

Do not require Isaac for ordinary unit tests.

### Campaign
- one iteration;
- budget stop;
- pause;
- resume;
- stop;
- invalid model proposal retry;
- model API error handling;
- Isaac error handling;
- waiting for manual Reactor assessment.

Do not call OpenAI or Reactor in unit tests.

Provide:

```text
FakeResearchModel
FakeIsaacClient
FakeReactorExecutor
```

---

# 23. OpenAI live-validation procedure

After unit tests pass, perform only a bounded live validation.

Use the real OpenAI API only after `OPENAI_API_KEY` is configured in the host environment.

Validation sequence:

1. Create one research campaign with a small objective.
2. Create/persist the Responses API conversation or first response state.
3. Generate **one** structured research proposal without running Isaac.
4. Inspect the stored proposal.
5. Confirm no unsupported parameters/world operations exist.
6. Compile it.
7. Start/check the long-lived Isaac worker in the container.
8. Execute exactly one bounded Isaac experiment from the compiled proposal.
9. If the existing Reactor pathway is ready for this compiled pair, execute one bounded Reactor side; otherwise record the limitation rather than fabricating it.
10. Persist all outputs.
11. Verify one complete research iteration survives process restart.
12. Stop.

Do not start an unattended multi-hour autonomous campaign in this milestone.

---

# 24. Container launch / lifecycle

Inspect `docs/AWS_ISAAC_HANDOFF.md` and the current container invocation before writing commands.

Create a documented launch method for the long-lived worker.

Conceptually it should use:

```text
--gpus all
--network host
ACCEPT_EULA=Y
PRIVACY_CONSENT=Y
repo mounted read/write at /workspace/project
runs accessible on the host
worker listening on host loopback only
```

Do not expose the worker port through the AWS security group.

The worker launch command must be reproducible and documented.

If Isaac 6.0.1 teardown remains problematic, document a controlled disposable-worker shutdown strategy, but do not use `os._exit()` after every experiment if a stable multi-experiment worker is achievable.

---

# 25. Documentation to add

Add/update:

```text
docs/INTELLIGENT_RESEARCH_HARNESS.md
docs/ISAAC_WORKER_PROTOCOL.md
```

The docs must explain:

- host vs container architecture;
- Responses API role;
- agent memory/state;
- SQLite vs OpenAI conversation state;
- ResearchAgent responsibilities;
- world-authoring boundary;
- why normal campaigns do not use Codex SDK;
- IsaacClient / IsaacWorker protocol;
- campaign state machine;
- recovery;
- Plan C integration;
- security boundaries;
- one-iteration AWS validation.

Update `AGENTS.md` only as needed.

---

# 26. Explicit non-goals for this milestone

Do **not** implement:

- Codex SDK as the normal runtime research agent;
- self-modifying source code;
- autonomous code-generation inside campaigns;
- arbitrary shell/terminal tools for the research model;
- an unrestricted Omniverse API surface exposed directly to the LLM;
- a huge asset crawler/index;
- automatic VLM Reactor assessment unless already implemented and specifically necessary;
- multi-agent frameworks such as CrewAI/LangGraph merely for orchestration;
- another major dashboard redesign;
- public network exposure of Isaac worker/dashboard;
- an unbounded autonomous experiment loop.

---

# 27. Minimum acceptance criteria

This milestone is complete when the following works:

```text
1. Host research campaign created
2. Objective persisted
3. Agent memory/state initialized
4. OpenAI Responses API produces one structured proposal
5. Proposal is validated against real capabilities
6. ScenarioCompiler creates a compiled experiment
7. Host IsaacClient sends it to the running Isaac container worker
8. IsaacWorker applies allowed experiment/world changes through Isaac/Omniverse APIs
9. Isaac executes and returns artifacts/state/result
10. Existing recording/persistence indexes the run
11. Campaign iteration is persisted
12. OpenAI conversation/response state is persisted
13. Campaign can be restarted and reconstruct its state
14. Existing dashboard/API can read the current campaign state
15. No Codex CLI/SDK is required at runtime
```

If Reactor can cleanly participate in the same first iteration, include it and use the existing Plan C comparator.

If not, stop with the Isaac intelligent-loop proof rather than introducing fake Reactor semantics.

---

# 28. Final report to me

When implementation is finished, stop and report:

1. baseline and final test counts;
2. every file added/changed;
3. exact host/container architecture implemented;
4. Isaac worker launch command;
5. Isaac worker protocol/endpoints;
6. OpenAI Responses API integration used;
7. how Responses state is stored (`conversation` or `previous_response_id`);
8. SQLite schema additions for research memory/state;
9. ResearchProposal schema;
10. supported parameter search space;
11. supported world-authoring operations;
12. how asset discovery/spawning currently works;
13. how a proposal is compiled into Isaac/Reactor scenarios;
14. recovery behavior after host/worker restart;
15. exact command for one live research iteration;
16. exact dashboard/API endpoints added, if any;
17. blockers before enabling 5–10 autonomous iterations.

Then stop. Do not continue into additional features without review.

---

# Core architectural invariant

Keep this distinction explicit throughout the implementation:

```text
Responses API Research Agent
    decides WHAT controlled experiment to try

Host Harness
    validates, remembers, coordinates and records

Isaac Worker in container
    performs simulator-native scene/world operations

Reactor
    supplies neural-world visual evidence

Plan C
    compares qualified evidence

Codex CLI
    remains the engineer that changes the laboratory itself
```

The research agent may change **experiment state** through approved tools.

It may not change **laboratory source code** during a campaign.
