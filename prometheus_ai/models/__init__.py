"""PROMETHEUS Model Integration & Abstraction Layer.

Exports provider-independent protocols, structured output schemas, budget controls,
normalized exceptions, and concrete provider adapters.
"""

from prometheus_ai.models.anthropic_provider import AnthropicProvider
from prometheus_ai.models.budget import (
    BudgetLimits,
    BudgetTracker,
    CancellationToken,
)
from prometheus_ai.models.exceptions import (
    ModelAuthenticationError,
    ModelBudgetExceededError,
    ModelCancelledError,
    ModelConfigurationError,
    ModelContextLengthError,
    ModelError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelServiceUnavailableError,
    ModelTimeoutError,
)
from prometheus_ai.models.mock_provider import MockModelProvider
from prometheus_ai.models.openai_provider import OpenAIProvider
from prometheus_ai.models.provider import BaseModelProvider
from prometheus_ai.models.router import ModelRouter, get_model_provider
from prometheus_ai.models.sanitizer import sanitize_dict, sanitize_secrets
from prometheus_ai.models.structured_outputs import (
    AgentToolRequest,
    FinalReport,
    InvestigationHypothesis,
    InvestigationPlan,
    ProposedPatch,
    ReviewFinding,
    ReviewReport,
    TaskPlan,
    TaskStep,
)
from prometheus_ai.models.types import (
    ModelResponse,
    ModelUsage,
    ToolCallRequest,
    calculate_estimated_cost,
)

__all__ = [
    "AgentToolRequest",
    # Concrete Providers & Routing
    "AnthropicProvider",
    # Core Protocols & Types
    "BaseModelProvider",
    # Budgets & Controls
    "BudgetLimits",
    "BudgetTracker",
    "CancellationToken",
    "FinalReport",
    # Structured Output Schemas
    "InvestigationHypothesis",
    "InvestigationPlan",
    "MockModelProvider",
    "ModelAuthenticationError",
    "ModelBudgetExceededError",
    "ModelCancelledError",
    "ModelConfigurationError",
    "ModelContextLengthError",
    # Exceptions
    "ModelError",
    "ModelInvalidResponseError",
    "ModelRateLimitError",
    "ModelResponse",
    "ModelRouter",
    "ModelServiceUnavailableError",
    "ModelTimeoutError",
    "ModelUsage",
    "OpenAIProvider",
    "ProposedPatch",
    "ReviewFinding",
    "ReviewReport",
    "TaskPlan",
    "TaskStep",
    "ToolCallRequest",
    "calculate_estimated_cost",
    "get_model_provider",
    "sanitize_dict",
    # Security
    "sanitize_secrets",
]
