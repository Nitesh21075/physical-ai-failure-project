"""Run the bounded Phase 2 Isaac Sim experiment from the Isaac container.

Example (inside the mounted project directory):
    ./python.sh scripts/run_isaac_phase2.py --runs-dir /workspace/runs
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from harness.agents.isaac import IsaacPlanarVelocityController
from harness.agents.mock import StaticScenarioAgent
from harness.environments.isaac_sim import IsaacSim50Runtime, IsaacSimEnvironment
from harness.evaluation.rule_based import RuleBasedEvaluator
from harness.orchestration.loop import Orchestrator
from harness.recording.trajectory import TrajectoryRecorder
from harness.schemas import Scenario


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Phase 2 Isaac Sim reference experiment."
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        required=True,
        help="Directory for trajectory artifacts",
    )
    parser.add_argument(
        "--disable-camera",
        action="store_true",
        help="Diagnostic mode: run physics without creating an RTX camera.",
    )
    args = parser.parse_args()

    scenario = Scenario(
        environment="isaac_sim",
        task="reach_target",
        seed=42,
        parameters={"target_position": [2.0, 0.0], "physics_steps_per_action": 12},
        # The reference run is a failure experiment: once the collapse occurs,
        # it is terminal.  This records the consequence while keeping the
        # headless container smoke test deterministic and bounded.
        hazards={"collapse_after_actions": 3, "terminal_on_collapse": True},
    )
    runtime = IsaacSim50Runtime(
        sensor_output_dir=None if args.disable_camera else args.runs_dir / "camera"
    )
    environment = IsaacSimEnvironment(runtime)
    orchestrator = Orchestrator(
        environment=environment,
        scenario_agent=StaticScenarioAgent(scenario),
        robot_controller=IsaacPlanarVelocityController(),
        evaluator=RuleBasedEvaluator(),
        recorder=TrajectoryRecorder(args.runs_dir),
        max_steps=30,
    )
    try:
        record = orchestrator.run_one()
    except BaseException:
        traceback.print_exc()
        os._exit(1)
    print(json.dumps(record.to_dict(), indent=2, sort_keys=True), flush=True)
    # Isaac Sim 6.0.1 can abort while releasing active camera task groups.
    # Artifacts are synchronously written above, and this is a disposable
    # container process, so terminate without invoking Kit teardown.
    os._exit(0)


if __name__ == "__main__":
    main()
