"""Tool Selection and Investigation Strategy Policies.

Formal Specification:
----------------------
1. State Representation (x in R^19):
   - Category one-hot vector (9 dims)
   - Normalized step progress (1 dim, min(step / 10, 1.0))
   - Normalized candidate files count (1 dim, min(files / 5, 1.0))
   - Normalized issue text length (1 dim, min(chars / 500, 1.0))
   - Normalized history depth (1 dim, min(history_len / 10, 1.0))
   - Prior failure frequency (1 dim, min(fails / 5, 1.0))
   - Error context presence (1 dim, 1.0 if present else 0.0)
   - Specific error indicator flags: syntax error, test failure, missing file (3 dims)
   - Bias / Intercept term (1 dim, constant 1.0)

2. Action Space (A_t):
   - Discrete set strictly constrained to `context.available_tools`.
   - Invariant: A policy may never return an action outside `available_tools`.

3. Reward Function (R):
   - Multi-objective scalar combining step success, final resolution, cost, and latency:
     R = w_outcome * I(outcome == SUCCESS)
       + w_resolved * I(final_result == True)
       - w_failure * I(outcome == FAILURE)
       - w_cost * cost_usd
       - w_latency * min(latency_ms / 1000.0, 1.0)
       - w_invalid * I(action not in available_tools)

4. Constraints:
   - Tool authorization & sandbox compliance: action in `available_tools`.
   - Execution budgets: enforced by SafePolicyExecutor and BudgetEnforcer.
   - Robust fallback: experimental policies fall back to approved baseline upon error.

5. Data Requirements:
   - Minimum trace threshold (e.g., 5 traces per category/tool) before relying on learned priors.
"""

from __future__ import annotations

import logging
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from prometheus_ai.learning.strategy.schema import (
    ActionOutcome,
    ExecutionTrace,
    TaskCategory,
    ToolSelectionContext,
    ToolSelectionDecision,
)
from prometheus_ai.models.provider import BaseModelProvider

logger = logging.getLogger(__name__)


@dataclass
class RewardWeights:
    """Weights for the multi-objective reward formulation."""

    w_outcome: float = 1.0
    w_resolved: float = 2.0
    w_failure: float = 0.5
    w_cost: float = 5.0
    w_latency: float = 0.1
    w_invalid: float = 5.0


def compute_reward(trace: ExecutionTrace, weights: RewardWeights | None = None) -> float:
    """Compute multi-objective reward for an individual execution trace."""
    w = weights or RewardWeights()
    reward = 0.0

    if trace.chosen_action not in trace.available_tools:
        return -w.w_invalid

    if trace.outcome == ActionOutcome.SUCCESS:
        reward += w.w_outcome
    elif trace.outcome == ActionOutcome.FAILURE:
        reward -= w.w_failure

    if trace.final_evaluation_result is True:
        reward += w.w_resolved
    elif trace.final_evaluation_result is False:
        reward -= 0.5

    reward -= w.w_cost * trace.cost_usd
    reward -= w.w_latency * min(trace.latency_ms / 1000.0, 1.0)
    return reward


class StateFeaturizer:
    """Featurizes a ToolSelectionContext into a dense numerical vector x in R^19."""

    CATEGORIES: ClassVar[list[TaskCategory]] = list(TaskCategory)

    @classmethod
    def feature_dim(cls) -> int:
        # 9 (category one-hot) + 1 (step) + 1 (candidates) + 1 (text len)
        # + 1 (history len) + 1 (prior fails) + 1 (err present) + 3 (err types) + 1 (intercept)
        return len(cls.CATEGORIES) + 10

    @classmethod
    def featurize(cls, context: ToolSelectionContext) -> list[float]:
        features: list[float] = []

        # 1. One-hot task category (9 dims)
        for cat in cls.CATEGORIES:
            features.append(1.0 if context.task_category == cat else 0.0)

        # 2. Normalized step index (1 dim)
        features.append(min(context.step_index / 10.0, 1.0))

        # 3. Normalized candidate files (1 dim)
        features.append(min(len(context.candidate_files) / 5.0, 1.0))

        # 4. Normalized issue description length (1 dim)
        features.append(min(len(context.issue_description) / 500.0, 1.0))

        # 5. History depth (1 dim)
        features.append(min(len(context.recent_history) / 10.0, 1.0))

        # 6. Prior failure count in history (1 dim)
        prior_fails = sum(
            1 for h in context.recent_history if str(h.get("outcome", "")).lower() == "failure"
        )
        features.append(min(prior_fails / 5.0, 1.0))

        # 7. Error context presence (1 dim)
        err_text = (context.error_context or "").lower()
        has_err = 1.0 if len(err_text) > 0 else 0.0
        features.append(has_err)

        # 8. Error type indicators (3 dims)
        is_syntax = 1.0 if any(k in err_text for k in ["syntax", "indentation", "parse"]) else 0.0
        is_test_fail = (
            1.0 if any(k in err_text for k in ["assertion", "failed", "exit code"]) else 0.0
        )
        is_missing = (
            1.0
            if any(
                k in err_text
                for k in ["not found", "importerror", "modulenotfound", "filenotfound"]
            )
            else 0.0
        )
        features.extend([is_syntax, is_test_fail, is_missing])

        # 9. Intercept / Bias term (1 dim)
        features.append(1.0)

        return features


class BaseToolSelectionPolicy(ABC):
    """Abstract interface for all tool-selection and investigation strategy policies."""

    @property
    @abstractmethod
    def policy_id(self) -> str:
        """Unique identifier for the policy."""
        raise NotImplementedError

    @property
    @abstractmethod
    def policy_type(self) -> str:
        """Category descriptor: rule_based, llm_selected, experience_informed, bandit."""
        raise NotImplementedError

    @abstractmethod
    async def select_tool(self, context: ToolSelectionContext) -> ToolSelectionDecision:
        """Select the next tool action from context.available_tools."""
        raise NotImplementedError

    def update(self, traces: list[ExecutionTrace]) -> None:  # noqa: B027
        """Optional update/training step on newly observed execution traces."""
        pass


class RuleBasedToolPolicy(BaseToolSelectionPolicy):
    """Baseline 1: Fixed, transparent deterministic rule-based tool-selection strategy.

    Uses category-driven phase ordering and state cues to select next action.
    Guaranteed to strictly choose from context.available_tools.
    """

    def __init__(self, policy_id: str = "policy-rule-based-v1") -> None:
        self._policy_id = policy_id

    @property
    def policy_id(self) -> str:
        return self._policy_id

    @property
    def policy_type(self) -> str:
        return "rule_based"

    async def select_tool(self, context: ToolSelectionContext) -> ToolSelectionDecision:
        if not context.available_tools:
            return ToolSelectionDecision(
                selected_tool="",
                rationale="No tools available in authorized context",
                confidence=0.0,
                policy_id=self.policy_id,
            )

        avail = context.available_tools
        step = context.step_index
        cat = context.task_category

        # Step 0: Discovery / Status check
        if step == 0:
            for candidate in ["inspect_git_status", "list_permitted_files", "register_repository"]:
                if candidate in avail:
                    return ToolSelectionDecision(
                        selected_tool=candidate,
                        rationale=f"Step {step} initial state inspection for {cat.value}",
                        confidence=1.0,
                        policy_id=self.policy_id,
                    )

        # Step 1: Search / Localization
        if step == 1 or (not context.candidate_files and step < 3):
            if "search_source_code" in avail:
                return ToolSelectionDecision(
                    selected_tool="search_source_code",
                    rationale=f"Searching repository code for issue keywords in {cat.value}",
                    confidence=0.9,
                    suggested_args={"query": context.issue_description[:80]},
                    policy_id=self.policy_id,
                )

        # Step 2: Read candidate file
        if context.candidate_files and "read_bounded_file" in avail and step <= 3:
            return ToolSelectionDecision(
                selected_tool="read_bounded_file",
                rationale=f"Inspecting candidate file '{context.candidate_files[0]}'",
                confidence=0.95,
                suggested_args={
                    "file_path": context.candidate_files[0],
                    "start_line": 1,
                    "end_line": 100,
                },
                policy_id=self.policy_id,
            )

        # Steps 3+: Test execution or patch verification
        if cat in (TaskCategory.REPRODUCTION, TaskCategory.REGRESSION, TaskCategory.FLAKY_TEST):
            if "run_allowlisted_tests" in avail:
                return ToolSelectionDecision(
                    selected_tool="run_allowlisted_tests",
                    rationale=f"Executing allowlisted tests to reproduce/verify {cat.value}",
                    confidence=0.95,
                    policy_id=self.policy_id,
                )

        if "inspect_git_diff" in avail and step >= 3:
            return ToolSelectionDecision(
                selected_tool="inspect_git_diff",
                rationale="Reviewing git diff for proposed changes",
                confidence=0.85,
                policy_id=self.policy_id,
            )

        if "apply_patch" in avail and step >= 2:
            return ToolSelectionDecision(
                selected_tool="apply_patch",
                rationale="Applying targeted patch repair",
                confidence=0.85,
                policy_id=self.policy_id,
            )

        if "run_allowlisted_tests" in avail:
            return ToolSelectionDecision(
                selected_tool="run_allowlisted_tests",
                rationale="Verifying system health through test runner",
                confidence=0.8,
                policy_id=self.policy_id,
            )

        # Default fallback to first authorized available tool
        selected = avail[0]
        return ToolSelectionDecision(
            selected_tool=selected,
            rationale=f"Default rule fallback to first authorized tool '{selected}'",
            confidence=0.5,
            policy_id=self.policy_id,
        )


class LLMToolPolicy(BaseToolSelectionPolicy):
    """Baseline 2: LLM-selected tool strategy.

    Queries the language model with task context and authorized tools.
    Falls back to a safe rule-based baseline if the LLM hallucinates or fails.
    """

    def __init__(
        self,
        model_provider: BaseModelProvider | None = None,
        fallback_policy: BaseToolSelectionPolicy | None = None,
        policy_id: str = "policy-llm-v1",
    ) -> None:
        self.model_provider = model_provider
        self.fallback_policy = fallback_policy or RuleBasedToolPolicy()
        self._policy_id = policy_id

    @property
    def policy_id(self) -> str:
        return self._policy_id

    @property
    def policy_type(self) -> str:
        return "llm_selected"

    async def select_tool(self, context: ToolSelectionContext) -> ToolSelectionDecision:
        if not context.available_tools:
            return ToolSelectionDecision(
                selected_tool="",
                rationale="No tools available",
                confidence=0.0,
                policy_id=self.policy_id,
            )

        if not self.model_provider:
            # Safe transparent fallback
            fallback_dec = await self.fallback_policy.select_tool(context)
            fallback_dec.is_fallback = True
            fallback_dec.rationale = f"LLM provider unavailable; {fallback_dec.rationale}"
            return fallback_dec

        prompt = (
            f"You are selecting the optimal next debugging tool.\n"
            f"Task Category: {context.task_category.value}\n"
            f"Issue: {context.issue_description}\n"
            f"Step: {context.step_index}\n"
            f"Available Tools: {', '.join(context.available_tools)}\n"
            f"Candidate Files: {context.candidate_files}\n"
            f"Select exactly ONE tool from the Available Tools list and explain your rationale."
        )

        try:
            if hasattr(self.model_provider, "generate"):
                response = await self.model_provider.generate(prompt=prompt)
            elif hasattr(self.model_provider, "generate_text"):
                response = await self.model_provider.generate_text(prompt=prompt)
            else:
                response = await self.model_provider(prompt)
            chosen_tool = None
            if hasattr(response, "content"):
                response_text = str(response.content).strip().lower()
            elif hasattr(response, "text"):
                response_text = str(response.text).strip().lower()
            else:
                response_text = str(response).strip().lower()

            # Find matching available tool mentioned in response
            for tool in context.available_tools:
                pattern = r"\b" + re.escape(tool.lower()) + r"\b"
                if re.search(pattern, response_text):
                    chosen_tool = tool
                    break

            if chosen_tool and chosen_tool in context.available_tools:
                return ToolSelectionDecision(
                    selected_tool=chosen_tool,
                    rationale=f"LLM selection: {response_text[:120].strip()}",
                    confidence=0.85,
                    policy_id=self.policy_id,
                    metadata={"provider": self.model_provider.model_id},
                )

            # Invalid tool chosen by LLM -> Fallback
            logger.warning(
                f"LLM produced unallowlisted tool output: '{response_text[:80]}'. "
                f"Triggering approved fallback policy."
            )
            fallback_dec = await self.fallback_policy.select_tool(context)
            fallback_dec.is_fallback = True
            fallback_dec.rationale = (
                f"LLM suggested invalid action; safely fell back to {fallback_dec.selected_tool}"
            )
            return fallback_dec

        except Exception as exc:
            logger.warning(f"LLM tool policy encountered error: {exc}. Using fallback.")
            fallback_dec = await self.fallback_policy.select_tool(context)
            fallback_dec.is_fallback = True
            return fallback_dec


class ExperienceInformedToolPolicy(BaseToolSelectionPolicy):
    """Strategy 3A: Experience-informed empirical outcome analysis.

    Aggregates empirical success probability, task resolution rate, and cost efficiency
    from recorded execution traces.
    Uses an Upper Confidence Bound (UCB) heuristic across tool priors.
    """

    def __init__(
        self,
        fallback_policy: BaseToolSelectionPolicy | None = None,
        policy_id: str = "policy-experience-informed-v1",
        min_traces_required: int = 3,
        exploration_weight: float = 1.0,
    ) -> None:
        self.fallback_policy = fallback_policy or RuleBasedToolPolicy()
        self._policy_id = policy_id
        self.min_traces_required = min_traces_required
        self.exploration_weight = exploration_weight
        # Table of: (category, tool) -> stats dict
        self._stats: dict[tuple[str, str], dict[str, float]] = {}
        self._total_traces = 0

    @property
    def policy_id(self) -> str:
        return self._policy_id

    @property
    def policy_type(self) -> str:
        return "experience_informed"

    def update(self, traces: list[ExecutionTrace]) -> None:
        """Aggregate statistical priors from execution traces."""
        for t in traces:
            key = (t.task_category.value, t.chosen_action)
            if key not in self._stats:
                self._stats[key] = {
                    "count": 0.0,
                    "successes": 0.0,
                    "resolutions": 0.0,
                    "total_reward": 0.0,
                }
            s = self._stats[key]
            s["count"] += 1.0
            if t.outcome == ActionOutcome.SUCCESS:
                s["successes"] += 1.0
            if t.final_evaluation_result is True:
                s["resolutions"] += 1.0
            s["total_reward"] += compute_reward(t)
            self._total_traces += 1

    async def select_tool(self, context: ToolSelectionContext) -> ToolSelectionDecision:
        if not context.available_tools:
            return ToolSelectionDecision(
                selected_tool="",
                rationale="No tools available",
                confidence=0.0,
                policy_id=self.policy_id,
            )

        cat = context.task_category.value
        avail = context.available_tools

        # Check data requirements
        cat_traces = sum(s["count"] for (c, t), s in self._stats.items() if c == cat)
        if cat_traces < self.min_traces_required:
            fallback_dec = await self.fallback_policy.select_tool(context)
            fallback_dec.is_fallback = True
            fallback_dec.rationale = (
                f"Insufficient historical data ({cat_traces}/{self.min_traces_required} traces); "
                f"using transparent fallback: {fallback_dec.selected_tool}"
            )
            return fallback_dec

        # Score candidate available tools using UCB formula:
        # score = empirical_mean_reward + c * sqrt(ln(N) / n_a)
        best_tool = None
        best_score = -float("inf")
        rationale = ""

        total_cat_n = max(1.0, cat_traces)

        for tool in avail:
            key = (cat, tool)
            s = self._stats.get(key)
            if s and s["count"] > 0:
                mean_reward = s["total_reward"] / s["count"]
                exploration = self.exploration_weight * math.sqrt(
                    math.log(total_cat_n + 1.0) / s["count"]
                )
                score = mean_reward + exploration
                reason = (
                    f"prior success rate {s['successes'] / s['count']:.2f}, "
                    f"resolved rate {s['resolutions'] / s['count']:.2f}"
                )
            else:
                # Optimism in the face of uncertainty for unvisited authorized tools
                score = 0.5 + self.exploration_weight * math.sqrt(math.log(total_cat_n + 1.0))
                reason = "exploring novel authorized tool with prior optimism"

            if score > best_score:
                best_score = score
                best_tool = tool
                rationale = reason

        if best_tool:
            return ToolSelectionDecision(
                selected_tool=best_tool,
                rationale=f"Experience-informed selection: {best_tool} ({rationale})",
                confidence=min(1.0, max(0.1, 1.0 / (1.0 + math.exp(-best_score)))),
                policy_id=self.policy_id,
                metadata={"empirical_score": best_score, "category_traces": cat_traces},
            )

        # Fallback if no tool scored
        fallback_dec = await self.fallback_policy.select_tool(context)
        fallback_dec.is_fallback = True
        return fallback_dec


class ContextualBanditToolPolicy(BaseToolSelectionPolicy):
    """Strategy 3B: Disjoint Linear Upper Confidence Bound (LinUCB) Contextual Bandit.

    Maintains a ridge regression model (A_a, b_a) for each candidate tool.
    Maps featurized state vector x in R^d to expected reward:
        theta_a = A_a^(-1) * b_a
        score_a = x^T * theta_a + alpha * sqrt(x^T * A_a^(-1) * x)
    Picks argmax over context.available_tools.
    """

    def __init__(
        self,
        fallback_policy: BaseToolSelectionPolicy | None = None,
        policy_id: str = "policy-linucb-v1",
        alpha: float = 0.5,
        min_traces_required: int = 5,
        regularization: float = 1.0,
    ) -> None:
        self.fallback_policy = fallback_policy or RuleBasedToolPolicy()
        self._policy_id = policy_id
        self.alpha = alpha
        self.min_traces_required = min_traces_required
        self.regularization = regularization
        self.d = StateFeaturizer.feature_dim()

        # For each tool name: A_a (d x d matrix), b_a (d-dim vector), count (int)
        self._A: dict[str, list[list[float]]] = {}
        self._b: dict[str, list[float]] = {}
        self._counts: dict[str, int] = {}

    @property
    def policy_id(self) -> str:
        return self._policy_id

    @property
    def policy_type(self) -> str:
        return "contextual_bandit"

    def _init_tool_state(self, tool: str) -> None:
        """Initialize ridge regression matrices for tool if not present."""
        if tool not in self._A:
            # Identity matrix * regularization lambda
            eye = [
                [self.regularization if i == j else 0.0 for j in range(self.d)]
                for i in range(self.d)
            ]
            self._A[tool] = eye
            self._b[tool] = [0.0] * self.d
            self._counts[tool] = 0

    def _invert_matrix(self, A: list[list[float]]) -> list[list[float]]:
        """Invert a symmetric positive-definite d x d matrix using Gauss-Jordan."""
        n = len(A)
        # Augment with identity
        aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]

        for i in range(n):
            # Pivot
            pivot = aug[i][i]
            if abs(pivot) < 1e-9:
                # Add small ridge damping if ill-conditioned
                pivot += 1e-4
            inv_p = 1.0 / pivot
            for j in range(2 * n):
                aug[i][j] *= inv_p
            for k in range(n):
                if k != i:
                    factor = aug[k][i]
                    for j in range(2 * n):
                        aug[k][j] -= factor * aug[i][j]

        return [row[n:] for row in aug]

    def _mat_vec_mult(self, M: list[list[float]], v: list[float]) -> list[float]:
        return [sum(M[i][j] * v[j] for j in range(len(v))) for i in range(len(M))]

    def _dot(self, v1: list[float], v2: list[float]) -> float:
        return sum(a * b for a, b in zip(v1, v2, strict=False))

    def update(self, traces: list[ExecutionTrace]) -> None:
        """Update LinUCB ridge regression matrices with execution traces."""
        for t in traces:
            tool = t.chosen_action
            self._init_tool_state(tool)

            # Reconstruct context from trace to featurize
            ctx = ToolSelectionContext(
                task_id=t.task_id,
                task_category=t.task_category,
                issue_description=str(t.initial_state.get("issue_description", "")),
                step_index=t.step_index,
                candidate_files=t.initial_state.get("candidate_files", []),
                available_tools=t.available_tools,
                recent_history=t.metadata.get("history", []),
                error_context=t.metadata.get("error_context"),
            )
            x = StateFeaturizer.featurize(ctx)
            r = compute_reward(t)

            # Update A_a += x * x^T
            A = self._A[tool]
            b = self._b[tool]
            for i in range(self.d):
                xi = x[i]
                b[i] += r * xi
                for j in range(self.d):
                    A[i][j] += xi * x[j]

            self._counts[tool] += 1

    async def select_tool(self, context: ToolSelectionContext) -> ToolSelectionDecision:
        if not context.available_tools:
            return ToolSelectionDecision(
                selected_tool="",
                rationale="No tools available",
                confidence=0.0,
                policy_id=self.policy_id,
            )

        avail = context.available_tools
        total_training_samples = sum(self._counts.values())

        # Check data requirements
        if total_training_samples < self.min_traces_required:
            fallback_dec = await self.fallback_policy.select_tool(context)
            fallback_dec.is_fallback = True
            fallback_dec.rationale = (
                f"LinUCB below minimum sample threshold ({total_training_samples}/{self.min_traces_required}); "
                f"falling back to {fallback_dec.selected_tool}"
            )
            return fallback_dec

        x = StateFeaturizer.featurize(context)

        best_tool = None
        best_score = -float("inf")

        for tool in avail:
            self._init_tool_state(tool)
            try:
                A_inv = self._invert_matrix(self._A[tool])
                # theta_a = A_inv * b_a
                theta = self._mat_vec_mult(A_inv, self._b[tool])
                # Expected reward = x^T * theta
                mean_est = self._dot(x, theta)
                # Exploration bonus = alpha * sqrt(x^T * A_inv * x)
                A_inv_x = self._mat_vec_mult(A_inv, x)
                var = max(0.0, self._dot(x, A_inv_x))
                ucb_bonus = self.alpha * math.sqrt(var)
                score = mean_est + ucb_bonus

                if score > best_score:
                    best_score = score
                    best_tool = tool
            except Exception as exc:
                logger.warning(f"LinUCB calculation failed for tool {tool}: {exc}")
                continue

        if best_tool and best_tool in avail:
            conf = 1.0 / (1.0 + math.exp(-max(-5.0, min(5.0, best_score))))
            return ToolSelectionDecision(
                selected_tool=best_tool,
                rationale=f"LinUCB Bandit selection (score: {best_score:.3f}, total_samples: {total_training_samples})",
                confidence=conf,
                policy_id=self.policy_id,
                metadata={"score": best_score, "tool_samples": self._counts.get(best_tool, 0)},
            )

        # Invariant: Fallback
        fallback_dec = await self.fallback_policy.select_tool(context)
        fallback_dec.is_fallback = True
        return fallback_dec
