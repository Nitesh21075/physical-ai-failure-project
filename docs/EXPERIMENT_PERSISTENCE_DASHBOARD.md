# Experiment Persistence and Plan C Review Dashboard

## Data boundary

`runs/` is authoritative. It contains the immutable scenario, trajectory,
evaluation, raw Isaac camera arrays, and native Reactor evidence. The ignored
`runs/experiments.sqlite3` database is a compact, reconstructable index only.
It contains IDs, outcomes, scenario metadata, paths, Plan C comparison fields,
and the mutable human review state. It never embeds frames, trajectories, or
video bytes.

Rebuild or update the index and generate derived media from existing artifacts:

```bash
.venv/bin/python scripts/reindex_runs.py --runs-dir runs --database runs/experiments.sqlite3
```

For Isaac runs, this preserves `.npy` RGBA arrays and writes derived files under
`<run>/media/isaac_replay/`: PNG preview frames, `thumbnail.png`, `replay.mp4`,
and `media.json`. Invalid/empty early camera arrays are preserved but skipped by
the exporter. For Reactor, `media/reactor/media.json` lists the ordered saved
sequence and native summary reference. When saved frames are available,
reindexing also derives `media/reactor/replay.mp4` for playback while preserving
the source frames; it makes no physical-state claim.

## Dashboard

Start only on the AWS workstation loopback interface:

```bash
.venv/bin/python scripts/run_dashboard.py --database runs/experiments.sqlite3 --port 8000
```

Available routes:

- `/` — paired Plan C experiments plus standalone recorded runs.
- `/pairs/<pair_id>` — side-by-side Plan C review and Isaac event timeline.
- `/experiments/<run_id>` — standalone experiment replay, artifacts, and timeline.
- `/api/experiments` — indexed experiment JSON.
- `/api/experiments/<run_id>` — standalone experiment view data.
- `/api/overview` — pair and standalone-run data used by the index page.
- `/api/pairs` — indexed pair JSON.
- `/api/pairs/<pair_id>` — pair detail JSON used by the UI.
- `PUT /api/pairs/<pair_id>/review` — persists one allowed review state.
- `/artifacts/<artifact_id>` — a stored, local artifact reference.

The detail view explicitly labels Isaac as **PHYSICS-GROUNDED SIMULATION** and
Reactor as **NEURAL WORLD VISUAL EVIDENCE**. Reactor chunk/media sequence timing
is separate from the Isaac simulation timeline; the dashboard does not claim
their clocks are synchronized.

From Windows PowerShell, leave the dashboard bound to loopback and tunnel it
over SSH:

```powershell
ssh -N -L 8000:127.0.0.1:8000 ubuntu@<AWS_PUBLIC_DNS_OR_IP>
```

Then open `http://127.0.0.1:8000/` locally. This needs no AWS security-group
rule or unauthenticated public port.

## Human review

Review state is deliberately mutable database metadata, not a rewrite of raw
evidence. Allowed values are `unreviewed`, `valid_discrepancy`,
`bad_world_model_generation`, `bad_scenario`, `simulator_artifact`, and
`inconclusive`. This creates a conservative future feedback signal without
implementing autonomous experiment selection.
