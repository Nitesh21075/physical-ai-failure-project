# AGENTS.md

## Project purpose

Build the Physical AI Failure Research Harness described in `docs/PROJECT.md`.

The immediate implementation target is Plan B: a modular closed-loop research harness for generating, executing, evaluating, and recording robot experiments in interchangeable environments.

## Read first

Before making architectural changes, read:

1. `docs/PROJECT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/PLANS.md`

## Core architectural rule

Keep the environment backend abstract. Do not couple the orchestrator to Isaac Sim.

The environment abstraction should conceptually support:

- `reset(...)`
- `step(action)`
- `observe()`
- `close()`

Initial backends:

- a local/mock environment for development and tests
- Isaac Sim on the AWS workstation
- a Reactor/neural-world backend if the hackathon credentials expose a suitable closed-loop API

Plan C should be possible by running the same experiment against multiple backends.

## Development environment

Local development:
- WSL2
- Ubuntu 24.04 LTS recommended
- ordinary Python tooling
- Git/GitHub

Simulation:
- AWS Linux GPU workstation
- Isaac Sim in Docker
- project repository mounted from the AWS host into the Isaac Sim container

Do not require Isaac Sim to be installed on the developer's Windows/WSL machine.

NVIDIA currently recommends the Isaac Sim container for remote/headless/cloud deployments. Keep simulator-specific dependencies isolated in the simulator backend/container.

## Coding principles

- Prefer small, explicit interfaces over large agent frameworks.
- Keep orchestration deterministic and inspectable.
- Use structured schemas for scenarios, actions, observations, trajectories, and evaluation results.
- Keep LLM/world-model calls behind adapters.
- Never put API keys in source control.
- Avoid committing generated trajectories, videos, simulator caches, or large assets.
- Add tests for backend-independent logic so most of the harness can be developed without Isaac Sim.
- Do not claim that a generative video world model provides structured physical state unless its actual API does so.
- Treat neural-world outputs and physics-simulator state as distinct data types.

## Runtime roles

- **Orchestrator:** runs experiments and controls the loop.
- **Scenario agent:** proposes/searches experiments using structured history.
- **Robot controller/policy:** maps observations to actions.
- **Environment:** executes actions and returns observations.
- **Evaluator:** determines task outcome and, importantly, environmental consequences/failures.
- **Recorder:** stores trajectories and metadata.
- **Memory:** compact structured experiment history, not an unbounded chat transcript.

## Plan C requirement

The same scenario/action sequence should be representable across backends whenever possible so that neural-world and physics-world results can be compared.

Do not prematurely implement Plan C-specific logic in the core orchestrator. Add comparison as a separate layer.

## Agentic coding

Codex/Claude Code may be used extensively during development. They are development tools, not required runtime components.

When a requested feature requires Isaac Sim APIs, inspect the installed/container version and current NVIDIA documentation rather than guessing API names.
