"""
Vorte Prompt Management
========================
Prompt versioning, registry, and templating system.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class PromptVersion:
    """A versioned prompt."""
    version: int
    content: str
    model: str = ""
    variables: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    is_active: bool = True


class PromptRegistry:
    """Registry for managing versioned prompts."""

    def __init__(self):
        self._prompts: Dict[str, List[PromptVersion]] = {}

    def register(self, name: str, content: str, version: Optional[int] = None, model: str = "") -> PromptVersion:
        """Register a new prompt version."""
        if name not in self._prompts:
            self._prompts[name] = []

        versions = self._prompts[name]
        if version is None:
            version = max((v.version for v in versions), default=0) + 1

        # Deactivate previous versions
        for v in versions:
            v.is_active = False

        prompt_version = PromptVersion(
            version=version,
            content=content,
            model=model,
            variables=self._extract_variables(content),
            is_active=True,
        )
        versions.append(prompt_version)
        return prompt_version

    def get(self, name: str, version: Optional[int] = None) -> Optional[str]:
        """Get a prompt by name and version (latest if not specified)."""
        versions = self._prompts.get(name, [])
        if not versions:
            return None

        if version is not None:
            for v in versions:
                if v.version == version:
                    return v.content
            return None

        # Return latest active version
        active = [v for v in versions if v.is_active]
        if active:
            return active[-1].content
        return versions[-1].content

    def render(self, name: str, variables: Dict[str, Any], version: Optional[int] = None) -> Optional[str]:
        """Render a prompt template with variables."""
        template = self.get(name, version)
        if not template:
            return None
        for key, value in variables.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))
        return template

    def list_prompts(self) -> Dict[str, int]:
        """List all prompts with their latest version."""
        return {name: max(v.version for v in versions) for name, versions in self._prompts.items()}

    def list_versions(self, name: str) -> List[Dict]:
        """List all versions of a prompt."""
        return [
            {"version": v.version, "model": v.model, "created_at": v.created_at, "is_active": v.is_active}
            for v in self._prompts.get(name, [])
        ]

    def delete(self, name: str) -> bool:
        """Delete all versions of a prompt."""
        return self._prompts.pop(name, None) is not None

    def clear(self) -> None:
        """Clear all prompts."""
        self._prompts.clear()

    @staticmethod
    def _extract_variables(template: str) -> List[str]:
        """Extract variable names from a template string."""
        import re
        return list(set(re.findall(r'\{\{\s*(\w+)\s*\}\}', template)))
