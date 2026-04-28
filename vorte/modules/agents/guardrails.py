"""
Vorte AI Guardrails
====================
AI safety guardrails for content filtering, PII detection, language enforcement,
and token budget management.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class GuardrailResult:
    """Result of a guardrail check."""
    allowed: bool = True
    modified_input: Optional[str] = None
    reason: str = ""
    score: float = 0.0


class Guardrail(ABC):
    """Base guardrail interface."""

    @abstractmethod
    async def check(self, text: str, context: Optional[Dict[str, Any]] = None) -> GuardrailResult:
        pass


class NoPIIGuardrail(Guardrail):
    """Detects and redacts personally identifiable information."""

    PII_PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
        "ipv4": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
    }

    def __init__(self, action: str = "redact"):
        self._action = action  # "redact" or "block"
        self._compiled = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in self.PII_PATTERNS.items()}

    async def check(self, text: str, context: Optional[Dict] = None) -> GuardrailResult:
        modified = text
        found_pii = []

        for name, pattern in self._compiled.items():
            matches = pattern.findall(modified)
            if matches:
                found_pii.append(name)
                if self._action == "redact":
                    modified = pattern.sub(f"[{name.upper()}_REDACTED]", modified)

        if found_pii:
            if self._action == "block":
                return GuardrailResult(allowed=False, reason=f"PII detected: {', '.join(found_pii)}")
            return GuardrailResult(allowed=True, modified_input=modified, reason=f"PII redacted: {', '.join(found_pii)}")
        return GuardrailResult(allowed=True)


class NoHarmfulContentGuardrail(Guardrail):
    """Checks for harmful or toxic content."""

    HARMFUL_PATTERNS = [
        r'\b(kill|murder|harm|hurt)\s+(yourself|someone|anyone|people)\b',
        r'\bhow to (make|create|build)\s+(a )?(bomb|weapon|explosive)\b',
        r'\b(illegal|illicit)\s+(activity|substance|drug)\b',
    ]

    def __init__(self):
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self.HARMFUL_PATTERNS]

    async def check(self, text: str, context: Optional[Dict] = None) -> GuardrailResult:
        for pattern in self._compiled:
            if pattern.search(text):
                return GuardrailResult(allowed=False, reason="Potentially harmful content detected")
        return GuardrailResult(allowed=True)


class LanguageGuardrail(Guardrail):
    """Enforces language constraints."""

    # Common language detection patterns (simplified)
    LANGUAGE_PATTERNS = {
        "en": r"(?i)\b(the|is|are|was|were|have|has|had|will|would|could|should)\b",
        "fr": r"(?i)\b(le|la|les|un|une|des|est|sont|été|avoir|être)\b",
        "sw": r"(?i)\b(na|ni|ya|wa|tu|wetu|hii|kile|amini|tunaweza)\b",
    }

    def __init__(self, allowed: Optional[List[str]] = None):
        self._allowed = set(allowed or ["en"])

    async def check(self, text: str, context: Optional[Dict] = None) -> GuardrailResult:
        # Simplified: check if the text matches any allowed language pattern
        words = text.split()
        if not words:
            return GuardrailResult(allowed=True)

        for lang in self._allowed:
            pattern = self.LANGUAGE_PATTERNS.get(lang)
            if pattern and re.search(pattern, text):
                return GuardrailResult(allowed=True)

        return GuardrailResult(allowed=False, reason=f"Text does not match allowed languages: {', '.join(self._allowed)}")


class TokenBudgetGuardrail(Guardrail):
    """Enforces token budget limits."""

    def __init__(self, max_tokens: int = 2000):
        self._max_tokens = max_tokens

    async def check(self, text: str, context: Optional[Dict] = None) -> GuardrailResult:
        # Rough estimation: ~1.3 tokens per word for English
        estimated_tokens = int(len(text.split()) * 1.3)
        if estimated_tokens > self._max_tokens:
            return GuardrailResult(
                allowed=False,
                reason=f"Input exceeds token budget: ~{estimated_tokens} tokens (max: {self._max_tokens})"
            )
        return GuardrailResult(allowed=True, score=estimated_tokens / self._max_tokens)


class GuardrailChain:
    """Runs multiple guardrails in sequence."""

    def __init__(self, guardrails: Optional[List[Guardrail]] = None):
        self._guardrails = guardrails or []

    def add(self, guardrail: Guardrail) -> "GuardrailChain":
        self._guardrails.append(guardrail)
        return self

    async def check(self, text: str, context: Optional[Dict] = None) -> GuardrailResult:
        current_text = text
        for guardrail in self._guardrails:
            result = await guardrail.check(current_text, context)
            if not result.allowed:
                return result
            if result.modified_input:
                current_text = result.modified_input
        return GuardrailResult(allowed=True, modified_input=current_text if current_text != text else None)
