"""Run exactly one host-side research proposal and Isaac worker experiment."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from harness.persistence import ExperimentStore
from harness.research import (
    CampaignExecutor,
    IsaacClient,
    IsaacPythonServerClient,
    ResearchAgent,
    ResearchCampaignStore,
    ScenarioCompiler,
    isaac_v0_capabilities,
)
from harness.research.openai_responses import OpenAIResponsesResearchModel


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("runs") / "experiments.sqlite3")
    parser.add_argument("--objective", default="Find the deterministic support-release boundary in the Isaac v0 reference scene.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--worker-url", default=None)
    parser.add_argument(
        "--isaac-transport",
        choices=("nvidia-python-server", "http"),
        default=None,
        help="Use the verified NVIDIA in-Kit server (default) or the legacy HTTP prototype.",
    )
    parser.add_argument("--python-server-address", default=None)
    parser.add_argument("--python-server-token", default=None)
    args = parser.parse_args()
    load_env(PROJECT_ROOT / ".env")
    model_name = args.model or os.environ.get("RESEARCH_MODEL", "gpt-5.6-luna")
    transport = args.isaac_transport or os.environ.get("ISAAC_TRANSPORT", "nvidia-python-server")
    if transport == "nvidia-python-server":
        isaac = IsaacPythonServerClient(
            args.python_server_address
            or os.environ.get("ISAAC_PYTHON_SERVER_ADDRESS", "127.0.0.1:8226"),
            auth_token=args.python_server_token or os.environ.get("ISAAC_PYTHON_SERVER_TOKEN", ""),
        )
    else:
        worker_url = args.worker_url or os.environ.get("ISAAC_WORKER_URL", "http://127.0.0.1:8211")
        isaac = IsaacClient(worker_url)
    research_store = ResearchCampaignStore(args.database)
    capabilities = isaac_v0_capabilities()
    campaign_id = research_store.create_campaign(
        args.objective,
        experiment_budget=1,
        model_provider="openai",
        model_name=model_name,
        capability_version=capabilities.version,
        simulator_metadata={
            "container_image": "nvcr.io/nvidia/isaac-sim:6.0.1",
            "transport": transport,
            "worker_protocol": "v1",
            "camera": "disabled: legacy camera render path stalls in this verified runtime",
        },
    )
    agent = ResearchAgent(research_store, OpenAIResponsesResearchModel(model_name), ScenarioCompiler(), capabilities)
    iteration_id = CampaignExecutor(research_store, ExperimentStore(args.database), agent, isaac).run_one_isaac_iteration(campaign_id)
    print({"campaign_id": campaign_id, "iteration": research_store.get_iteration(iteration_id)})


if __name__ == "__main__":
    main()
