# Plan C: Capability-Gated Neural vs Physics Comparison

Plan C compares a matched Isaac Sim experiment with a matched Reactor visual
session without changing the core `Environment` or `Orchestrator` contracts.
The implementation is in `harness.comparison`, so single-backend Plan B runs
remain unchanged.

## What constitutes a matched experiment

`MatchedExperimentSpec` declares the common task and seed, one backend-specific
scenario for Isaac Sim, one for a qualified Reactor model, and the degree of
action alignment. Both recorded experiments are then bound to that declaration
as a `MatchedExperiment`.

- `exact`: both backends executed a linked common action sequence. This is
  supported for a future shared action adapter; the sequence reference is
  required.
- `semantic`: different native actions represent documented common intent. This
  is supported, but the result is explicitly a visual-vs-physics comparison.
- `unavailable`: no defensible action mapping exists. The pair can be
  persisted, but it is never compared.

The current Phase 2 and Phase 3 adapters have different action vocabularies:
Isaac accepts planar velocity while Reactor accepts camera/navigation controls.
Therefore their current pairs must use `semantic` alignment and document the
mapping. They must not claim exact replay.

## Evidence and authority

Isaac `EvaluationResult.environmental_failure` is the physics-grounded outcome
for this v0 comparison. Reactor's generated media is represented by a separate
`VisualEventAssessment` that carries:

- the event label being reviewed;
- an observed / not-observed / indeterminate decision;
- confidence;
- media references; and
- assessor provenance.

A Reactor `EvaluationResult` is intentionally not used to establish a physical
outcome. `PlanCComparator` emits one of:

- `not_comparable` when no action alignment exists;
- `inconclusive` when no visual assessment exists, the evidence is
  indeterminate, or confidence is below threshold;
- `consistent_visual_evidence` when qualified video evidence agrees with the
  Isaac outcome; or
- `candidate_discrepancy` when qualified video evidence differs from Isaac.

A candidate discrepancy is a review queue item, not a proven world-model or
physics error. The linked evidence and native trajectories must be inspected
before drawing that conclusion.

## Executing and recording a pair

`PlanCCoordinator` accepts two narrow executors that run supplied scenarios and
return normal `ExperimentRecord` values. It validates the returned backends and
scenario identities, invokes `PlanCComparator`, then writes:

```text
runs/paired/<pair_id>/comparison.json
```

The JSON contains both normal experiment records, the match declaration, the
comparison status, and only artifact references. It does not copy video or
Isaac sensor arrays. This is the paired-dataset metadata required for research
and later review.

## AWS validation sequence

1. Pull the repository on the AWS host and run the ordinary backend-neutral
   test suite inside the Isaac container.
2. Run the Phase 2 Isaac smoke script to create the physics trajectory.
3. Use a Reactor transport that persists generated chunks, then run the matched
   Reactor scenario with the declared semantic action mapping.
4. Create a `VisualEventAssessment` from reviewed/annotated chunk evidence and
   run the coordinator to write the paired dataset entry.

The current Plan C tests use deterministic executors and media references; they
do not call Reactor or consume API credits. A concrete production
`ReactorSession` transport that captures chunk artifacts remains the necessary
runtime integration step before a live Reactor/Isaac paired run.
