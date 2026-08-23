"""Serve the local Plan C review dashboard; bind only to loopback by default."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from harness.dashboard import create_app
from harness.persistence import ExperimentStore


def load_project_env(path: Path = Path(".env")) -> None:
    """Load simple project-local KEY=VALUE entries without replacing shell settings."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key.replace("_", "").isalnum() and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("runs") / "experiments.sqlite3")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(ExperimentStore(args.database)), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
