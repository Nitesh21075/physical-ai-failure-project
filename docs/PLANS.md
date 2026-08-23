# Plans

## Plan B — Immediate build

**Robot Failure Research Harness / Environmental Failure Lab**

Build reusable infrastructure that can:
- generate/select scenarios;
- run a robot controller;
- execute actions in an environment;
- evaluate environmental consequences;
- record trajectories;
- maintain structured experiment memory;
- iterate automatically.

Initial environment backend: Isaac Sim.

Goal: make the harness useful independently of the exact neural-world API.

## Plan A — Neural world model as the simulator

If Reactor provides access to a robotics world-model environment with closed-loop observation/action interaction, make that the primary environment.

Conceptually:

```text
robot policy
   -> observation/action
   -> neural world model
   -> next observation
   -> robot policy
   -> ...
   -> evaluator
```

The LLM should primarily act as experiment director/researcher rather than manually specifying every physical event. It can define high-level objectives and choose promising regions of the experiment space while the world model supplies the simulated experience.

If the model itself supports world-action prediction/planning, exploit that rather than duplicating it with an LLM.

Isaac Sim becomes optional validation/reference infrastructure rather than the main simulator.

## Plan C — Neural world vs physics world

Run equivalent experiments in:
- a neural world model;
- Isaac Sim/PhysX.

Compare the resulting trajectories and environmental consequences.

Search especially for:
- neural/physics disagreement;
- rare environmental failures;
- failure boundaries;
- cases where one environment predicts a catastrophic consequence and the other does not.

Record paired data such as:

```text
initial state
action sequence
neural observation trajectory
physics observation/state trajectory
neural outcome
physics outcome
difference
```

This creates a research dataset for evaluating and potentially improving world models on rare physical events.

The analogy is an autoresearch loop:

```text
generate experiment
    -> run neural world
    -> run physics world
    -> compare
    -> identify interesting discrepancy
    -> generate next experiment
    -> repeat
```

## Relationship

Plan B is the foundation.

Plan A is a specialized neural-world backend/use case of the harness.

Plan C adds a second environment and a comparison/research loop.

Do not implement all three at once.
