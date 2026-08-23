"""Host-side, persistent research-campaign primitives.

This package deliberately has no Isaac or OpenAI import at module load time.
"""

from harness.research.agent import ResearchAgent
from harness.research.assets import (
    AssetCatalog,
    AssetCatalogError,
    AssetMetadata,
    isaac_v0_asset_catalog,
)
from harness.research.campaign import CampaignState, ResearchCampaignStore
from harness.research.compiler import CompiledExperiment, ScenarioCompiler
from harness.research.execution import CampaignExecutor
from harness.research.isaac_client import IsaacClient, IsaacPythonServerClient, IsaacWorkerError
from harness.research.model import ResearchModel, ResearchModelResult
from harness.research.schemas import ExperimentProposal, ResearchProposalError
from harness.research.search_space import WorldCapabilities, isaac_v0_capabilities
from harness.research.visual_assessment import (
    OpenAIResponsesVisualAssessor,
    VisualAssessmentError,
    VisualComparisonAssessment,
    VisualComparisonRequest,
)
from harness.research.world_prompt import (
    OpenAIResponsesWorldPromptModel,
    WorldPromptError,
    WorldPromptRequest,
)

__all__ = [
    "AssetCatalog",
    "AssetCatalogError",
    "AssetMetadata",
    "CampaignExecutor",
    "CampaignState",
    "CompiledExperiment",
    "ExperimentProposal",
    "IsaacClient",
    "IsaacPythonServerClient",
    "IsaacWorkerError",
    "ResearchAgent",
    "ResearchCampaignStore",
    "ResearchModel",
    "ResearchModelResult",
    "ResearchProposalError",
    "ScenarioCompiler",
    "OpenAIResponsesVisualAssessor",
    "VisualAssessmentError",
    "VisualComparisonAssessment",
    "VisualComparisonRequest",
    "OpenAIResponsesWorldPromptModel",
    "WorldPromptError",
    "WorldPromptRequest",
    "WorldCapabilities",
    "isaac_v0_asset_catalog",
    "isaac_v0_capabilities",
]
