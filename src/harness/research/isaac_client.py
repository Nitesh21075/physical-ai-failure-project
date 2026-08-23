"""Host-side localhost JSON client.  It intentionally imports no Isaac modules."""

from __future__ import annotations

import json
import socket
from dataclasses import asdict, is_dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


class IsaacWorkerError(RuntimeError):
    pass


class IsaacClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8211", *, timeout_seconds: float = 180.0) -> None:
        if not base_url.startswith("http://127.0.0.1:"):
            raise ValueError("Isaac worker URL must bind to 127.0.0.1")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def capabilities(self) -> dict[str, Any]:
        return self._request("GET", "/capabilities")

    def reset_session(self, campaign_id: str) -> dict[str, Any]:
        return self._request("POST", "/session/reset", {"campaign_id": campaign_id})

    def run_experiment(self, compiled_experiment: Any, *, campaign_id: str, iteration_id: str) -> dict[str, Any]:
        payload = asdict(compiled_experiment) if is_dataclass(compiled_experiment) else compiled_experiment
        return self._request("POST", "/experiment/run", {"campaign_id": campaign_id, "iteration_id": iteration_id, "experiment": payload})

    def experiment_status(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/experiment/status/{run_id}")

    def experiment_result(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/experiment/result/{run_id}")

    def close_session(self) -> dict[str, Any]:
        return self._request("POST", "/session/close", {})

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"request_id": str(uuid4()), "schema_version": "v1", **(payload or {})}).encode()
        request = Request(self.base_url + path, data=body, method=method, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise IsaacWorkerError(f"Isaac worker request {method} {path} failed: {error}") from error
        if not result.get("success", False):
            raise IsaacWorkerError(result.get("error", {}).get("message", "Isaac worker returned an error"))
        return result.get("result", {})


class IsaacPythonServerClient:
    """Client for NVIDIA's local ``isaacsim.code_editor.python_server``.

    The submitted source is constant and imports the typed dispatcher above;
    compiler output travels only as JSON arguments, never executable code.
    """

    # Top-level await is the Python Server's supported way to run Kit work.
    # It writes the typed response to captured output because multi-line code
    # is treated as statements rather than as one result expression.
    _RUN_CODE = """\
import json
import sys
if '/workspace/project/src' not in sys.path:
    sys.path.insert(0, '/workspace/project/src')
from harness.isaac_worker.kit_rpc import run_experiment
print(json.dumps(await run_experiment(compiled_experiment, campaign_id, iteration_id)))
"""

    def __init__(
        self,
        address: str = "127.0.0.1:8226",
        *,
        auth_token: str = "",
        timeout_seconds: float = 300.0,
    ) -> None:
        host, separator, port = address.rpartition(":")
        if not separator or host != "127.0.0.1" or not port.isdigit():
            raise ValueError("Isaac Python Server must bind only to 127.0.0.1:PORT")
        self.host, self.port = host, int(port)
        self.auth_token, self.timeout_seconds = auth_token, timeout_seconds

    def run_experiment(
        self, compiled_experiment: Any, *, campaign_id: str, iteration_id: str
    ) -> dict[str, Any]:
        experiment = asdict(compiled_experiment) if is_dataclass(compiled_experiment) else compiled_experiment
        response = self._send(
            {
                "auth_token": self.auth_token,
                "code": self._RUN_CODE,
                "context": "physical_ai_harness",
                "args": {
                    "compiled_experiment": experiment,
                    "campaign_id": campaign_id,
                    "iteration_id": iteration_id,
                },
                "timeout": int(self.timeout_seconds),
            }
        )
        if response.get("status") != "ok":
            raise IsaacWorkerError(response.get("evalue", "Isaac Python Server returned an error"))
        output = response.get("output", "")
        try:
            result = json.loads(output.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as error:
            raise IsaacWorkerError("Isaac Python Server returned no typed result") from error
        if not isinstance(result, dict) or not result.get("success", False):
            message = result.get("error", {}).get("message") if isinstance(result, dict) else None
            raise IsaacWorkerError(message or "Isaac worker returned an invalid response")
        return result["result"]

    def _send(self, envelope: dict[str, Any]) -> dict[str, Any]:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout_seconds) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.sendall(json.dumps(envelope).encode("utf-8"))
                connection.shutdown(socket.SHUT_WR)
                chunks: list[bytes] = []
                while data := connection.recv(65536):
                    chunks.append(data)
        except OSError as error:
            raise IsaacWorkerError(f"Isaac Python Server request failed: {error}") from error
        try:
            response = json.loads(b"".join(chunks))
        except json.JSONDecodeError as error:
            raise IsaacWorkerError("Isaac Python Server returned invalid JSON") from error
        if not isinstance(response, dict):
            raise IsaacWorkerError("Isaac Python Server returned a non-object response")
        return response
