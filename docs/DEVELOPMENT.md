# Development and Deployment

## Local development

Recommended:
- Windows host
- WSL2
- Ubuntu 24.04 LTS
- Git
- Python virtual environment

The local machine does not need Isaac Sim or a GPU for the backend-independent parts of the harness.

Use local mocks/tests to develop:
- schemas
- orchestrator
- scenario logic
- memory
- recorder
- evaluator
- backend interfaces

## GitHub

GitHub is the source of truth.

Recommended flow:

```text
local WSL
   -> git commit
   -> git push
GitHub
   -> git pull
AWS workstation
```

Do not commit:
- secrets
- AWS credentials
- Reactor API keys
- Isaac Sim caches
- generated videos
- large simulator assets
- local virtual environments

Use `.env` locally and a secrets mechanism/environment variables on AWS.

## AWS Isaac Sim workstation

The AWS Linux GPU workstation is the real simulation machine.

Expected structure:

```text
/home/<user>/physical-ai-failure-harness/
~/docker/isaac-sim/
```

The project should live on the AWS host, not only inside the Isaac Sim container.

The Isaac Sim container mounts the project directory so scripts can be executed inside the simulator environment.

Conceptually:

```text
AWS host
  /home/<user>/physical-ai-failure-harness
             |
             | bind mount
             v
Isaac Sim container
  /workspace/physical-ai-failure-harness
```

Keep simulator caches/logs/data in their own host directories.

## Isaac Sim

The current NVIDIA documentation recommends the Docker/container deployment for remote headless/cloud servers. Use the installed version on the AWS workstation as the source of truth for API compatibility.

Do not hard-code an Isaac Sim version in application logic unless the workstation is intentionally pinned to that version.

Use headless/streaming operation for automated runs where appropriate.

## Coding agents

Codex or Claude Code can be used on the local WSL machine and/or AWS host.

They are development agents, not required runtime components.

A coding agent should:
- read `AGENTS.md`;
- read the architecture docs;
- inspect actual installed simulator/API versions;
- implement small testable changes;
- run backend-independent tests locally;
- run Isaac-specific tests only on AWS.

## Future CI

The first version does not need GPU CI.

Keep the majority of tests backend-independent so GitHub Actions can validate them without Isaac Sim.
