"""
Vorte AI Module - Cost Tracker
================================
Tracks token usage and estimated costs per provider and model.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from vorte.modules.ai.schemas import (
    AIResponse,
    CostReportEntry,
    TokenUsage,
)

logger = logging.getLogger("vorte.ai.cost_tracker")


# ---------------------------------------------------------------------------
# Pricing data (USD per 1K tokens, approximate – update periodically)
# ---------------------------------------------------------------------------

# Prices per 1,000 tokens: (input, output)
# fmt: off
_DEFAULT_PRICING: Dict[str, Dict[str, tuple[float, float]]] = {
    "openai": {
        "gpt-4o":             (2.50, 10.00),
        "gpt-4o-mini":        (0.150, 0.600),
        "gpt-4-turbo":        (10.00, 30.00),
        "gpt-4":              (30.00, 60.00),
        "gpt-3.5-turbo":      (0.50, 1.50),
        "o1-preview":         (15.00, 60.00),
        "o1-mini":            (3.00, 12.00),
        "text-embedding-3-small": (0.020, 0.0),
        "text-embedding-3-large": (0.130, 0.0),
        "text-embedding-ada-002":  (0.100, 0.0),
    },
    "anthropic": {
        "claude-sonnet-4-20250514":  (3.00, 15.00),
        "claude-3-5-sonnet-20241022": (3.00, 15.00),
        "claude-3-5-haiku-20241022":  (0.80, 4.00),
        "claude-3-opus-20240229":     (15.00, 75.00),
    },
    "gemini": {
        "gemini-2.0-flash":     (0.075, 0.300),
        "gemini-1.5-pro":       (1.25, 5.00),
        "gemini-1.5-flash":     (0.075, 0.300),
        "text-embedding-004":   (0.018, 0.0),
    },
    "mistral": {
        "mistral-large-latest": (2.00, 6.00),
        "mistral-medium-latest": (2.70, 8.10),
        "mistral-small-latest": (0.20, 0.60),
        "open-mistral-nemo":    (0.025, 0.025),
        "mistral-embed":        (0.010, 0.0),
    },
}
# fmt: on


@dataclass
class UsageRecord:
    """A single usage record."""
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: float
    timestamp: float  # Unix timestamp
    request_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class CostTracker:
    """
    Tracks token usage and costs across all providers and models.

    Features:
    * Real-time cost estimation using per-model pricing tables
    * Period-based reports (hourly, daily, weekly, monthly)
    * Usage history with optional persistence hooks
    * Budget alerts
    """

    def __init__(
        self,
        pricing: Optional[Dict[str, Dict[str, tuple[float, float]]]] = None,
        budget_limit: Optional[float] = None,
        max_history: int = 100_000,
    ) -> None:
        self._pricing = pricing or _DEFAULT_PRICING
        self._budget_limit = budget_limit
        self._max_history = max_history
        self._history: List[UsageRecord] = []
        self._total_cost: float = 0.0
        self._on_record_hooks: List[Any] = []

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    def set_pricing(
        self, provider: str, model: str, input_per_1k: float, output_per_1k: float
    ) -> None:
        """Set pricing for a specific provider + model."""
        if provider not in self._pricing:
            self._pricing[provider] = {}
        self._pricing[provider][model] = (input_per_1k, output_per_1k)

    def get_pricing(self, provider: str, model: str) -> tuple[float, float]:
        """Get (input, output) price per 1K tokens. Returns (0, 0) if unknown."""
        return self._pricing.get(provider, {}).get(model, (0.0, 0.0))

    def estimate_cost(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Estimate the USD cost for a request."""
        input_price, output_price = self.get_pricing(provider, model)
        cost = (prompt_tokens * input_price / 1000) + (completion_tokens * output_price / 1000)
        return cost

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        response: AIResponse,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UsageRecord:
        """Record token usage from an AI response."""
        return self.record_raw(
            provider=response.provider,
            model=response.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            request_id=response.request_id,
            metadata=metadata or response.metadata,
        )

    def record_raw(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        request_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UsageRecord:
        """Record usage with raw token counts."""
        total = prompt_tokens + completion_tokens
        cost = self.estimate_cost(provider, model, prompt_tokens, completion_tokens)

        record = UsageRecord(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            estimated_cost=cost,
            timestamp=time.time(),
            request_id=request_id,
            metadata=metadata or {},
        )

        self._history.append(record)
        self._total_cost += cost

        # Trim history
        if len(self._history) > self._max_history:
            removed = self._history[: len(self._history) - self._max_history]
            self._history = self._history[-self._max_history:]
            self._total_cost -= sum(r.estimated_cost for r in removed)

        # Budget alert
        if self._budget_limit is not None and self._total_cost >= self._budget_limit:
            logger.warning(
                "Budget limit reached: $%.2f / $%.2f",
                self._total_cost,
                self._budget_limit,
            )

        # Hooks
        for hook in self._on_record_hooks:
            try:
                hook(record)
            except Exception as exc:
                logger.warning("Cost tracker hook error: %s", exc)

        return record

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def total_cost(self) -> float:
        return self._total_cost

    @property
    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self._history)

    @property
    def total_requests(self) -> int:
        return len(self._history)

    def cost_by_provider(self) -> Dict[str, float]:
        result: Dict[str, float] = defaultdict(float)
        for r in self._history:
            result[r.provider] += r.estimated_cost
        return dict(result)

    def cost_by_model(self) -> Dict[str, float]:
        result: Dict[str, float] = defaultdict(float)
        for r in self._history:
            key = f"{r.provider}/{r.model}"
            result[key] += r.estimated_cost
        return dict(result)

    def tokens_by_provider(self) -> Dict[str, Dict[str, int]]:
        result: Dict[str, Dict[str, int]] = defaultdict(lambda: {"prompt": 0, "completion": 0, "total": 0})
        for r in self._history:
            result[r.provider]["prompt"] += r.prompt_tokens
            result[r.provider]["completion"] += r.completion_tokens
            result[r.provider]["total"] += r.total_tokens
        return dict(result)

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def report(
        self,
        period: str = "all",
        since: Optional[float] = None,
    ) -> List[CostReportEntry]:
        """
        Generate a cost report.

        Args:
            period: "all", "hourly", "daily", "weekly", "monthly"
            since: Optional Unix timestamp to filter from.
        """
        now = time.time()
        if period == "hourly":
            since = since or (now - 3600)
        elif period == "daily":
            since = since or (now - 86400)
        elif period == "weekly":
            since = since or (now - 7 * 86400)
        elif period == "monthly":
            since = since or (now - 30 * 86400)
        else:
            since = since or 0

        filtered = [r for r in self._history if r.timestamp >= since]

        # Aggregate by (provider, model)
        agg: Dict[tuple, Dict[str, Any]] = {}
        for r in filtered:
            key = (r.provider, r.model)
            if key not in agg:
                agg[key] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost": 0.0,
                    "request_count": 0,
                    "min_ts": r.timestamp,
                    "max_ts": r.timestamp,
                }
            entry = agg[key]
            entry["prompt_tokens"] += r.prompt_tokens
            entry["completion_tokens"] += r.completion_tokens
            entry["total_tokens"] += r.total_tokens
            entry["estimated_cost"] += r.estimated_cost
            entry["request_count"] += 1
            entry["min_ts"] = min(entry["min_ts"], r.timestamp)
            entry["max_ts"] = max(entry["max_ts"], r.timestamp)

        report: List[CostReportEntry] = []
        for (prov, mdl), data in agg.items():
            report.append(CostReportEntry(
                provider=prov,
                model=mdl,
                prompt_tokens=data["prompt_tokens"],
                completion_tokens=data["completion_tokens"],
                total_tokens=data["total_tokens"],
                estimated_cost=round(data["estimated_cost"], 6),
                request_count=data["request_count"],
                period_start=datetime.fromtimestamp(data["min_ts"], tz=timezone.utc),
                period_end=datetime.fromtimestamp(data["max_ts"], tz=timezone.utc),
            ))

        return sorted(report, key=lambda x: x.estimated_cost, reverse=True)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    @property
    def history(self) -> List[UsageRecord]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
        self._total_cost = 0.0

    # ------------------------------------------------------------------
    # Hooks & budget
    # ------------------------------------------------------------------

    def on_record(self, hook) -> None:
        """Register a callback invoked after each usage record."""
        self._on_record_hooks.append(hook)

    def set_budget(self, limit: float) -> None:
        self._budget_limit = limit

    def check_budget(self) -> bool:
        """Return True if within budget (or no budget set)."""
        if self._budget_limit is None:
            return True
        return self._total_cost < self._budget_limit
