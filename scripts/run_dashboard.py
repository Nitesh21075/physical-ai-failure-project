"""Serve the local Plan C review dashboard; bind only to loopback by default."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from harness.dashboard import create_app
from harness.persistence import ExperimentStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("runs") / "experiments.sqlite3")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(ExperimentStore(args.database)), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
