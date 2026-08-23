# Roadmap

## Milestone 0 — Repository skeleton
- backend-neutral environment interface
- scenario/evaluation schemas
- experiment memory
- trajectory recorder
- mock environment tests

## Milestone 1 — Minimal Isaac Sim backend
- connect to the AWS Isaac Sim container
- load/spawn one robot and simple environment
- expose reset/step/observe
- capture camera + basic robot state
- implement one deterministic environmental hazard

## Milestone 2 — Closed-loop failure search
- scenario agent with structured output
- robot controller
- evaluator
- experiment loop
- persistent experiment records

## Milestone 3 — Neural-world backend
- determine exact Reactor robotics/world-model API available to the hackathon
- implement adapter without changing the orchestrator
- record neural trajectories

## Milestone 4 — Plan C
- run matched experiments in Isaac Sim and neural world
- compare trajectories/outcomes
- identify discrepancies and environmental failures
- build paired dataset

## Milestone 5 — Demo
- one visually clear environment
- 3–5 environmental failure mechanisms
- live experiment search
- replay a discovered failure
- show neural-vs-physics discrepancy if feasible
