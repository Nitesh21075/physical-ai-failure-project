"""Create and persist one bounded live Responses research proposal (no Isaac run)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from harness.research import (
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
    args = parser.parse_args()
    load_env(PROJECT_ROOT / ".env")
    model_name = args.model or os.environ.get("RESEARCH_MODEL", "gpt-5.6-luna")
    store = ResearchCampaignStore(args.database)
    campaign_id = store.create_campaign(args.objective, experiment_budget=1, model_provider="openai", model_name=model_name)
    agent = ResearchAgent(store, OpenAIResponsesResearchModel(model_name), ScenarioCompiler(), isaac_v0_capabilities())
    iteration_id, compiled = agent.propose_one(campaign_id)
    print({"campaign_id": campaign_id, "iteration_id": iteration_id, "proposal": compiled.proposal.to_dict()})


if __name__ == "__main__":
    main()
