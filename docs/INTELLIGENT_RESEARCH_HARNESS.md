# Intelligent research harness

This is the host-side foundation for a bounded, persistent research campaign.
It supplements the filesystem-authoritative experiment artifacts in `runs/`;
it does not store trajectories, frames, or media blobs in SQLite.

## Boundary

```text
Responses API ResearchModel -> ResearchAgent -> ScenarioCompiler -> IsaacPythonServerClient
                                      |                 |              |
                                      v                 v              v
                                campaign SQLite   existing Plan C    localhost worker
```

The research model decides which *validated experiment* to propose.  It has no
shell, Docker, source-editing, or direct simulator capability.  The host
validates the proposal against the installed harness capability registry before
anything reaches an Isaac worker.

## Current implementation

`harness.research` provides:

- `ExperimentProposal`: structured data only, with no arbitrary-code field;
- `isaac_v0_capabilities()`: only the parameters already accepted by
  `IsaacSimEnvironment` (`target_position`, `robot_start`,
  `physics_steps_per_action`, `collapse_after_actions`);
- `ScenarioCompiler`: produces an Isaac `Scenario` and, when a qualified
  Reactor model is supplied, an existing semantic `MatchedExperimentSpec`;
- `ResearchCampaignStore`: durable campaign, iteration, event, and operator
  instruction metadata in SQLite, including capability version and simulator
  provenance (the verified `nvcr.io/nvidia/isaac-sim:6.0.1` image tag);
- `OpenAIResponsesResearchModel`: strict JSON-schema Responses output, with
  persisted `previous_response_id` continuity; and
- `IsaacPythonServerClient` and `harness.isaac_worker.kit_rpc`: a host-only
  typed client and an in-Kit dispatcher backed by NVIDIA's Python Server. The
  dispatcher returns normal `ExperimentRecord` data for the existing
  index/recorder model. The legacy HTTP worker is retained only as a
  diagnostic prototype because it can block Kit's main event loop in 6.0.1.

The verified 6.0.1 path currently advertises a physics-only capability set:
the legacy camera renderer is disabled after it repeatedly stalled. A campaign
therefore receives no camera evidence rather than mislabeled or fabricated
sensor output; the worker capability response exposes that status explicitly.

The host package has no Isaac imports.  `world_edits` remain rejected until a
specific typed operation has been tested in the Isaac 6.0.1 worker. This is
deliberate: the verified scene supports only parameterized target/start poses,
bounded physics steps, and deterministic support release—not arbitrary scene
authoring.

`AssetCatalog` is intentionally an empty curated manifest in v0. Its
`list_asset_categories`, `search_assets`, and `inspect_asset` calls never scan
container paths; unknown IDs return `ASSET_NOT_AVAILABLE`. This is the asset
discovery boundary that later verified `spawn_asset` operations will use.

The persisted state vocabulary includes `STOPPING`, `RUNNING_REACTOR`, and
`COMPARING` for a later qualified Plan C path. The verified v0 loop performs
Isaac only and does not invent Reactor assessment or comparison results.

## Recovery

Iterations persist every state transition.  On restart, callers can inspect
`ResearchCampaignStore.incomplete_iterations()` and reconcile a worker/run ID
before any retry.  No incomplete iteration is automatically re-executed.

## Configuration and live validation

Install the optional SDK dependency with `pip install -e '.[research]'`, then
set `OPENAI_API_KEY`, `RESEARCH_MODEL_PROVIDER=openai`, and an explicit
`RESEARCH_MODEL` in `.env`. `gpt-5.6-luna` with low reasoning effort is the
economical default. Create one proposal without running Isaac:

```bash
.venv/bin/python scripts/validate_research_proposal.py \
  --database /tmp/research-validation.sqlite3
```

Start the container worker as documented in
[`ISAAC_WORKER_PROTOCOL.md`](ISAAC_WORKER_PROTOCOL.md), then use
`CampaignExecutor` for one bounded Isaac iteration. Do not start an unattended
campaign from this foundation.

The exact one-iteration host command is:

```bash
.venv/bin/python scripts/run_research_iteration.py \
  --database runs/experiments.sqlite3
```

## Optional visual assessment

`OpenAIResponsesVisualAssessor` sends deliberately small, labeled, ordered
sets of persisted Isaac and world-model PNG/JPEG/WEBP frames to the Responses
API. It returns both sources' visual reading; the world-model result is the
`VisualEventAssessment` supplied to Plan C. Neither is simulator state or
physical ground truth.

The Responses API supports image inputs, not a native `input_video` content
item, so sample representative frames from a recording rather than uploading
an MP4 as the assessment input. Invoke the standalone assessor with:

```bash
.venv/bin/python scripts/assess_visual_evidence.py \
  --event-type structural_collapse \
  --isaac-frame runs/<isaac-run>/media/frame_0001.png \
  --isaac-frame runs/<isaac-run>/media/frame_0012.png \
  --world-model-frame runs/<world-model-run>/media/frame_0001.png \
  --world-model-frame runs/<world-model-run>/media/frame_0012.png
```

## Dashboard API

The existing localhost dashboard additionally exposes:

- `GET/POST /api/campaigns`
- `GET /api/campaigns/{campaign_id}`
- `POST /api/campaigns/{campaign_id}/instructions`
- `POST /api/campaigns/{campaign_id}/pause|resume|stop`

These endpoints persist campaign state only; they do not expose repository,
shell, Docker, or arbitrary simulator commands.
