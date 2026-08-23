"""Coordinates one compiled Isaac iteration without granting the model execution power."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from harness.persistence.store import ExperimentStore
from harness.research.agent import ResearchAgent
from harness.research.campaign import IterationState, ResearchCampaignStore


class IsaacExecutor(Protocol):
    def run_experiment(self, compiled_experiment: object, *, campaign_id: str, iteration_id: str) -> dict: ...


class CampaignExecutor:
    def __init__(self, store: ResearchCampaignStore, experiment_store: ExperimentStore, agent: ResearchAgent, isaac: IsaacExecutor, *, runs_root: str | Path = "runs") -> None:
        self.store, self.experiment_store, self.agent, self.isaac = store, experiment_store, agent, isaac
        self.runs_root = Path(runs_root)

    def run_one_isaac_iteration(self, campaign_id: str) -> str:
        self.store.transition_campaign(campaign_id, "running")
        iteration_id, compiled = self.agent.propose_one(campaign_id)
        self.store.transition_iteration(iteration_id, IterationState.RUNNING_ISAAC)
        try:
            result = self.isaac.run_experiment(compiled, campaign_id=campaign_id, iteration_id=iteration_id)
            record = result["record"]
            self.experiment_store.upsert_experiment(record)
            self.store.record_isaac_run(iteration_id, result["run_id"])
            self.store.transition_iteration(iteration_id, IterationState.RECORDED)
            campaign = self.store.get_campaign(campaign_id)
            if campaign and campaign["experiments_used"] >= campaign["experiment_budget"]:
                self.store.transition_campaign(campaign_id, "completed", reason="experiment budget exhausted")
            return iteration_id
        except Exception as error:
            recovered = self._recover_isaac_artifact(compiled.isaac_scenario.scenario_id)
            if recovered is not None:
                self.experiment_store.upsert_experiment(recovered, run_directory=Path(recovered["trajectory_ref"]).parent)
                self.store.record_isaac_run(iteration_id, recovered["run_id"])
                self.store.transition_iteration(iteration_id, IterationState.RECORDED)
                self.store.transition_campaign(campaign_id, "completed", reason="recovered completed Isaac artifact")
                return iteration_id
            self.store.transition_iteration(iteration_id, IterationState.FAILED, error=str(error))
            self.store.transition_campaign(campaign_id, "paused", reason="Isaac execution failed; manual recovery required")
            raise

    def _recover_isaac_artifact(self, scenario_id: str) -> dict | None:
        """Reconcile an artifact written before an RPC client lost its response."""
        if not self.runs_root.is_dir():
            return None
        for scenario_path in self.runs_root.rglob("scenario.json"):
            try:
                scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
                metadata = json.loads((scenario_path.parent / "metadata.json").read_text(encoding="utf-8"))
                result = json.loads((scenario_path.parent / "result.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if scenario.get("scenario_id") == scenario_id and metadata.get("backend") == "isaac_sim":
                return {"run_id": metadata["run_id"], "backend": "isaac_sim", "scenario": scenario, "trajectory_ref": str(scenario_path.parent / "trajectory.jsonl"), "evaluation": result, "created_at": datetime.fromtimestamp((scenario_path.parent / "result.json").stat().st_mtime, UTC).isoformat()}
        return None
