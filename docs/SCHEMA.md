# Initial Data Schemas

These are deliberately minimal and will evolve.

## Scenario

```json
{
  "scenario_id": "uuid",
  "environment": "string",
  "task": "string",
  "seed": 0,
  "parameters": {},
  "hazards": {}
}
```

## Step result

```json
{
  "run_id": "uuid",
  "simulation_time": 0.0,
  "done": false,
  "observation_ref": null,
  "state": null,
  "events": []
}
```

## Final evaluation

```json
{
  "run_id": "uuid",
  "task_success": false,
  "environmental_failure": true,
  "failure_type": "structural_collapse",
  "severity": "high",
  "metrics": {},
  "evidence_refs": []
}
```

## Experiment record

```json
{
  "run_id": "uuid",
  "scenario": {},
  "trajectory_ref": "path/or/object-store-reference",
  "evaluation": {},
  "backend": "isaac_sim",
  "created_at": "ISO-8601"
}
```

## Important

Keep raw media and large tensors outside the Git repository. JSON/JSONL should contain metadata and references to artifacts.
