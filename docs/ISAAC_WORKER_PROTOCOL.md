# Isaac worker protocol (v1)

The verified Isaac Sim 6.0.1 transport uses NVIDIA's
`isaacsim.code_editor.python_server` inside the container. The host uses
`harness.research.IsaacPythonServerClient`; normal host imports never load
Isaac modules. The client submits one constant, audited dispatcher call and
passes the compiler output only as JSON arguments. The research model never
submits Python source or runs Docker commands.

Every request is JSON and includes:

```json
{"request_id":"uuid", "schema_version":"v1"}
```

Every response is either:

```json
{"success":true, "result":{}}
```

or:

```json
{"success":false, "error":{"code":"CAPABILITY_MISSING", "message":"..."}}
```

The typed dispatcher supports:

- `GET /health`
- `GET /capabilities`
- `POST /session/reset` with `campaign_id`
- `POST /experiment/run` with `campaign_id`, `iteration_id`, and a compiled experiment
- `GET /experiment/status/{run_id}`
- `GET /experiment/result/{run_id}`
- `POST /session/close`

The dispatcher lives in `harness.isaac_worker.kit_rpc` and owns one
`IsaacSimEnvironment` in Kit's own async event loop. It uses the initial v0
physics-only capability set because the legacy `isaacsim.sensors.camera`
render path stalls in this installed image; this is advertised as a disabled
sensor capability rather than silently producing invalid sensor evidence.

`scripts/run_isaac_worker.py` and the HTTP client remain a diagnostic
prototype. They are not the default 6.0.1 transport because a normal HTTP
handler can block Kit's application loop.
It accepts only the established v0 `isaac_sim` scenario parameters and the
`set_planar_velocity` controller path. World edits and asset spawning are
reported as unavailable rather than translated to arbitrary USD/Python.

Launch on the AWS host (the worker is reachable only on host loopback):

```bash
export ISAAC_PYTHON_SERVER_TOKEN="$(openssl rand -hex 32)"
sudo docker run -d --name physical-ai-nvidia-worker --gpus all --network host \
  --user 0:0 --entrypoint bash -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e HOME=/tmp \
  -e OMNI_KIT_ALLOW_ROOT=1 -e ISAAC_RUNS_DIR=/workspace/project/runs/isaac-nvidia-worker \
  -e ISAAC_PYTHON_SERVER_TOKEN \
  -v /home/ubuntu/physical-ai-failure-project:/workspace/project \
  nvcr.io/nvidia/isaac-sim:6.0.1 \
  -lc 'cd /isaac-sim && ./isaac-sim.sh --no-window \
       --enable isaacsim.code_editor.python_server \
       --/exts/isaacsim.code_editor.python_server/host=127.0.0.1 \
       --/exts/isaacsim.code_editor.python_server/port=8226 \
       --/exts/isaacsim.code_editor.python_server/require_auth=true \
       --/exts/isaacsim.code_editor.python_server/auth_token=$ISAAC_PYTHON_SERVER_TOKEN'
```

Wait for `app ready` in `docker logs physical-ai-nvidia-worker`, set the same
token in the ignored local `.env` as `ISAAC_PYTHON_SERVER_TOKEN`, then run one
bounded iteration from the host:

```bash
.venv/bin/python scripts/run_research_iteration.py --database runs/experiments.sqlite3
```

Do not publish port `8226` through Docker or an AWS security group. The
server is a powerful code-execution service, so it must remain loopback-only,
protected with its token, and invoked solely through the typed host client.
