"""Small localhost JSON protocol for a long-lived Isaac Sim worker."""

from __future__ import annotations

import json
import os
import queue
import threading
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from harness.agents.isaac import IsaacPlanarVelocityController
from harness.agents.mock import StaticScenarioAgent
from harness.environments.isaac_sim import IsaacSim50Runtime, IsaacSimEnvironment
from harness.evaluation.rule_based import RuleBasedEvaluator
from harness.orchestration.loop import Orchestrator, RunLimitExceeded
from harness.recording.trajectory import TrajectoryRecorder
from harness.schemas import Action, ExperimentRecord, Scenario, TrajectoryStep


class WorkerProtocolError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ExperimentRunner(Protocol):
    def run(self, scenario: Scenario) -> ExperimentRecord: ...

    def close(self) -> None: ...


class IsaacExperimentRunner:
    """The only class that starts simulator-native state, once per worker."""

    def __init__(
        self,
        runs_dir: Path,
        *,
        application: Any | None = None,
        enable_camera: bool = True,
    ) -> None:
        self.runs_dir = runs_dir
        self.environment = IsaacSimEnvironment(
            IsaacSim50Runtime(
                sensor_output_dir=runs_dir / "camera" if enable_camera else None,
                application=application,
            )
        )
        self.enable_camera = enable_camera

    def run(self, scenario: Scenario) -> ExperimentRecord:
        return Orchestrator(
            environment=self.environment,
            scenario_agent=StaticScenarioAgent(scenario),
            robot_controller=IsaacPlanarVelocityController(),
            evaluator=RuleBasedEvaluator(),
            recorder=TrajectoryRecorder(self.runs_dir),
            max_steps=30,
        ).run_one()

    async def run_async(self, scenario: Scenario) -> ExperimentRecord:
        """Run the same bounded experiment through the live Kit async loop."""
        run_id = str(uuid4())
        initial_observation = await self.environment.reset_async(scenario)
        session = TrajectoryRecorder(self.runs_dir).start_run(run_id, scenario, self.environment.backend_name)
        session.record_initial_observation(initial_observation)
        controller = IsaacPlanarVelocityController()
        evaluator = RuleBasedEvaluator()
        observation = initial_observation
        trajectory: list[TrajectoryStep] = []
        for index in range(30):
            action = controller.act(observation)
            if not isinstance(action, Action):
                raise TypeError("robot controller must return an Action")
            result = await self.environment.step_async(action)
            step = TrajectoryStep(index=index, observation=observation, action=action, result=result)
            trajectory.append(step)
            session.record_step(step)
            if result.done:
                break
            observation = result.observation
        else:
            raise RunLimitExceeded(f"experiment {run_id} did not finish within 30 steps")
        evaluation = evaluator.evaluate(scenario, initial_observation, tuple(trajectory))
        artifacts = session.finish(evaluation)
        return ExperimentRecord(
            run_id=run_id,
            scenario=scenario,
            backend=self.environment.backend_name,
            trajectory_ref=str(artifacts.trajectory_path),
            evaluation=evaluation,
            created_at=datetime.now(UTC).isoformat(),
        )

    def close(self) -> None:
        self.environment.close()


class IsaacWorker:
    """Validates protocol input and owns one lazy long-lived simulator runner."""

    protocol_version = "v1"

    def __init__(
        self,
        runs_dir: str | Path,
        runner: ExperimentRunner | None = None,
        *,
        queue_requests: bool = False,
        camera_available: bool = True,
    ) -> None:
        self.runs_dir = Path(runs_dir)
        self._runner = runner
        self._results: dict[str, dict[str, Any]] = {}
        self._iteration_runs: dict[tuple[str, str], dict[str, Any]] = {}
        self._closed = False
        self.queue_requests = queue_requests
        self.camera_available = camera_available
        self._requests: queue.Queue[tuple[str, str, dict[str, Any], threading.Event, dict[str, Any]]] = queue.Queue()

    def handle(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        try:
            if method == "GET" and path == "/health":
                return self._success({"protocol_version": self.protocol_version, "status": "ready"})
            self._validate_envelope(payload)
            if method == "GET" and path == "/capabilities":
                return self._success(self._capabilities())
            if method == "POST" and path == "/session/reset":
                self._required_text(payload, "campaign_id")
                return self._success({"status": "ready"})
            if method == "POST" and path == "/session/close":
                self.close()
                return self._success({"status": "closed"})
            if method == "POST" and path == "/experiment/run":
                return self._run(payload)
            if method == "GET" and path.startswith("/experiment/status/"):
                return self._lookup(path.removeprefix("/experiment/status/"), status_only=True)
            if method == "GET" and path.startswith("/experiment/result/"):
                return self._lookup(path.removeprefix("/experiment/result/"), status_only=False)
            raise WorkerProtocolError("NOT_FOUND", "unknown endpoint")
        except WorkerProtocolError as error:
            return {"success": False, "error": {"code": error.code, "message": str(error)}}
        except Exception as error:  # noqa: BLE001 - native simulator errors must not cross RPC
            return {"success": False, "error": {"code": "SIMULATOR_ERROR", "message": str(error)}}

    def close(self) -> None:
        if self._runner is not None and not self._closed:
            self._runner.close()
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

    def submit(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Queue a request for the Kit-owning main thread when configured."""
        if not self.queue_requests:
            return self.handle(method, path, payload)
        done = threading.Event()
        holder: dict[str, Any] = {}
        self._requests.put((method, path, payload, done, holder))
        if not done.wait(timeout=300):
            return {"success": False, "error": {"code": "WORKER_TIMEOUT", "message": "worker main thread did not service the request"}}
        return holder["response"]

    def process_next(self, timeout: float = 0.1) -> bool:
        """Run one queued RPC on the thread that initialized SimulationApp."""
        try:
            method, path, payload, done, holder = self._requests.get(timeout=timeout)
        except queue.Empty:
            return False
        holder["response"] = self.handle(method, path, payload)
        done.set()
        return True

    def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._closed:
            raise WorkerProtocolError("WORKER_CLOSED", "worker has been closed")
        self._required_text(payload, "campaign_id")
        self._required_text(payload, "iteration_id")
        idempotency_key = (payload["campaign_id"], payload["iteration_id"])
        if idempotency_key in self._iteration_runs:
            return self._success(self._iteration_runs[idempotency_key])
        experiment = payload.get("experiment")
        if not isinstance(experiment, dict) or not isinstance(experiment.get("isaac_scenario"), dict):
            raise WorkerProtocolError("INVALID_EXPERIMENT", "compiled experiment must include isaac_scenario")
        scenario = Scenario.from_dict(experiment["isaac_scenario"])
        if scenario.environment != "isaac_sim":
            raise WorkerProtocolError("INVALID_EXPERIMENT", "worker accepts only isaac_sim scenarios")
        runner = self._runner or IsaacExperimentRunner(self.runs_dir)
        self._runner = runner
        record = runner.run(scenario)
        result = {"run_id": record.run_id, "record": record.to_dict(), "status": "completed"}
        self._results[record.run_id] = result
        self._iteration_runs[idempotency_key] = result
        return self._success(result)

    async def run_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Asynchronous counterpart used only by NVIDIA's Kit Python Server."""
        try:
            self._validate_envelope(payload)
            if self._closed:
                raise WorkerProtocolError("WORKER_CLOSED", "worker has been closed")
            self._required_text(payload, "campaign_id")
            self._required_text(payload, "iteration_id")
            idempotency_key = (payload["campaign_id"], payload["iteration_id"])
            if idempotency_key in self._iteration_runs:
                return self._success(self._iteration_runs[idempotency_key])
            experiment = payload.get("experiment")
            if not isinstance(experiment, dict) or not isinstance(experiment.get("isaac_scenario"), dict):
                raise WorkerProtocolError("INVALID_EXPERIMENT", "compiled experiment must include isaac_scenario")
            scenario = Scenario.from_dict(experiment["isaac_scenario"])
            if scenario.environment != "isaac_sim":
                raise WorkerProtocolError("INVALID_EXPERIMENT", "worker accepts only isaac_sim scenarios")
            runner = self._runner or IsaacExperimentRunner(self.runs_dir)
            self._runner = runner
            run_async = getattr(runner, "run_async", None)
            if run_async is None:
                raise WorkerProtocolError("SIMULATOR_ERROR", "runner lacks Kit async execution support")
            record = await run_async(scenario)
            result = {"run_id": record.run_id, "record": record.to_dict(), "status": "completed"}
            self._results[record.run_id] = result
            self._iteration_runs[idempotency_key] = result
            return self._success(result)
        except WorkerProtocolError as error:
            return {"success": False, "error": {"code": error.code, "message": str(error)}}
        except Exception as error:  # noqa: BLE001 - native simulator errors must not cross RPC
            return {"success": False, "error": {"code": "SIMULATOR_ERROR", "message": str(error)}}

    def _lookup(self, run_id: str, *, status_only: bool) -> dict[str, Any]:
        if run_id not in self._results:
            raise WorkerProtocolError("RUN_NOT_FOUND", f"unknown run: {run_id}")
        result = self._results[run_id]
        return self._success({"run_id": run_id, "status": result["status"]} if status_only else result)

    def _capabilities(self) -> dict[str, Any]:
        return {
            "backend": "isaac_sim", "parameters": ["target_position", "robot_start", "physics_steps_per_action", "collapse_after_actions"],
            "world_operations": [], "actions": ["set_planar_velocity"],
            "sensors": ["camera_rgb"] if self.camera_available else [],
            "sensor_status": "available" if self.camera_available else "disabled: legacy camera render path is unavailable",
            "worker_protocol": self.protocol_version,
            "simulator": {
                "container_image": os.environ.get("ISAAC_CONTAINER_IMAGE", "nvcr.io/nvidia/isaac-sim:6.0.1"),
                "image_tag": "6.0.1",
                "stage_reset": "async create_new_stage/reset in Kit event loop",
            },
        }

    def _validate_envelope(self, payload: dict[str, Any]) -> None:
        if payload.get("schema_version") != self.protocol_version:
            raise WorkerProtocolError("UNSUPPORTED_SCHEMA", f"schema_version must be {self.protocol_version}")
        self._required_text(payload, "request_id")

    @staticmethod
    def _required_text(payload: dict[str, Any], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            raise WorkerProtocolError("INVALID_REQUEST", f"{name} must be a non-empty string")
        return value

    @staticmethod
    def _success(result: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "result": result}


def serve(worker: IsaacWorker, host: str = "127.0.0.1", port: int = 8211) -> None:
    if host != "127.0.0.1":
        raise ValueError("Isaac worker must bind only to 127.0.0.1")

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, status: HTTPStatus, body: dict[str, Any]) -> None:
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(status); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)

        def _dispatch(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}") if length else {}
                if not isinstance(payload, dict): raise TypeError("JSON request body must be an object")
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                self._respond(HTTPStatus.BAD_REQUEST, {"success": False, "error": {"code": "INVALID_JSON", "message": str(error)}}); return
            response = worker.submit(self.command, self.path, payload)
            self._respond(HTTPStatus.OK if response["success"] else HTTPStatus.BAD_REQUEST, response)

        do_GET = _dispatch
        do_POST = _dispatch

        def log_message(self, format: str, *args: Any) -> None: pass

    # One Kit process is a serial resource. Keeping HTTP request handling on
    # its main thread avoids calling USD/PhysX from an arbitrary Python thread.
    server = HTTPServer((host, port), Handler)
    server.serve_forever()
