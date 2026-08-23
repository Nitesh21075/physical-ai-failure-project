"""Rebuild the local experiment index from filesystem-authoritative runs/."""

from __future__ import annotations

import argparse
from pathlib import Path

from harness.persistence import ExperimentStore, reindex_runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--database", type=Path, default=Path("runs") / "experiments.sqlite3")
    args = parser.parse_args()
    print(reindex_runs(ExperimentStore(args.database), args.runs_dir))


if __name__ == "__main__":
    main()
