# Physical AI Failure Research Harness

An experimental harness for discovering and collecting rare environmental failure trajectories for physical AI.

The core idea is to run robot experiments in interchangeable environments (initially Isaac Sim, later neural world models such as Reactor) and record the resulting actions, observations, world state, and environmental consequences.

## Current plans

- **Plan B — Failure Research Harness:** build the reusable closed-loop orchestration/data-collection system first.
- **Plan A — Neural World Model Environment:** if the available world-model API supports closed-loop robotics interaction, make the neural world model the primary environment.
- **Plan C — Neural vs Physics:** run equivalent experiments in a neural world model and Isaac Sim, compare trajectories/outcomes, and collect high-value discrepancies and rare physical failures.

## Important definition of failure

A failure is not merely the robot failing its task.

The primary target is an **environmental failure/consequence caused or triggered by robot actions**, for example:

`robot action -> structural instability -> roof collapse`

Other examples include fire ignition/spread, falling beams/debris, secondary structural collapse, hazardous obstruction, or other high-penalty environmental events.

See `docs/PROJECT.md` and `docs/ARCHITECTURE.md` for the current design.
