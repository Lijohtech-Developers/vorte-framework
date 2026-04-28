"""
Conversation Memory System
==========================
Provides short-term and long-term conversation memory for agents.
Supports adding, retrieving, and clearing memory entries with configurable
window sizes and summarization.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryRole(str, Enum):
    """Roles for memory entries."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class MemoryEntry:
    """
    A single entry in conversation memory.

    Attributes:
        id: Unique identifier for the entry.
        role: The role of the speaker (user, assistant, system, tool).
        content: The text content of the message.
        timestamp: When the entry was created (Unix timestamp).
        metadata: Optional metadata associated with the entry.
        token_count: Approximate token count of the content.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: str = "user"
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_count: int = 0

    def __post_init__(self) -> None:
        """Estimate token count after initialization if not set."""
        if self.token_count == 0 and self.content:
            # Rough estimate: ~4 characters per token for English
            self.token_count = max(1, len(self.content) // 4)

    @property
    def datetime(self) -> datetime:
        """Get the timestamp as a datetime object."""
        return datetime.fromtimestamp(self.timestamp)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary representation."""
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "token_count": self.token_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MemoryEntry:
        """Create a MemoryEntry from a dictionary."""
        return cls(**data)

    def to_message(self) -> Dict[str, str]:
        """Convert to a message dict suitable for LLM APIs."""
        return {"role": self.role, "content": self.content}


@dataclass
class MemoryConfig:
    """
    Configuration for conversation memory.

    Attributes:
        max_turns: Maximum number of conversation turns to keep in short-term
            memory. A turn includes one user message and one assistant response.
        max_tokens: Maximum total tokens to keep in memory.
        enable_long_term: Whether to enable long-term memory summarization.
        long_term_summary_interval: Number of turns before creating a summary
            and moving older entries to long-term storage.
        include_timestamps: Whether to include timestamps in retrieved entries.
        include_metadata: Whether to include metadata in retrieved entries.
    """
    max_turns: int = 20
    max_tokens: int = 8192
    enable_long_term: bool = False
    long_term_summary_interval: int = 10
    include_timestamps: bool = False
    include_metadata: bool = False


@dataclass
class MemorySummary:
    """A summary of a set of memory entries for long-term storage."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    entry_count: int = 0
    timestamp: float = field(default_factory=time.time)
    token_count: int = 0
    covered_turns: int = 0


class ConversationMemory:
    """
    Manages conversation memory for an agent.

    Provides short-term memory with configurable turn windows and optional
    long-term memory through periodic summarization of older entries.

    Usage:
        memory = ConversationMemory(MemoryConfig(max_turns=10))

        # Add entries
        memory.add_user("Hello, how are you?")
        memory.add_assistant("I'm doing well, thanks for asking!")
        memory.add_system("You are a helpful assistant.")

        # Retrieve recent entries
        recent = memory.get_recent()
        recent = memory.get_recent(max_entries=5)

        # Get all entries as messages for LLM
        messages = memory.get_messages()

        # Clear memory
        memory.clear()
    """

    def __init__(self, config: Optional[MemoryConfig] = None) -> None:
        self._config = config or MemoryConfig()
        self._entries: List[MemoryEntry] = []
        self._long_term_summaries: List[MemorySummary] = []
        self._total_tokens: int = 0

    @property
    def config(self) -> MemoryConfig:
        """Get the memory configuration."""
        return self._config

    @property
    def entry_count(self) -> int:
        """Get the number of entries in short-term memory."""
        return len(self._entries)

    @property
    def total_tokens(self) -> int:
        """Get the total token count in short-term memory."""
        return self._total_tokens

    @property
    def long_term_summary_count(self) -> int:
        """Get the number of long-term summaries."""
        return len(self._long_term_summaries)

    # ---- Add Methods ----

    def add(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """
        Add a memory entry.

        Args:
            role: The role of the speaker (user, assistant, system, tool).
            content: The text content.
            metadata: Optional metadata.

        Returns:
            The created MemoryEntry.
        """
        entry = MemoryEntry(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        self._total_tokens += entry.token_count
        self._trim_if_needed()
        return entry

    def add_user(self, content: str, **kwargs: Any) -> MemoryEntry:
        """Convenience method to add a user message."""
        return self.add(MemoryRole.USER.value, content, **kwargs)

    def add_assistant(self, content: str, **kwargs: Any) -> MemoryEntry:
        """Convenience method to add an assistant message."""
        return self.add(MemoryRole.ASSISTANT.value, content, **kwargs)

    def add_system(self, content: str, **kwargs: Any) -> MemoryEntry:
        """Convenience method to add a system message."""
        return self.add(MemoryRole.SYSTEM.value, content, **kwargs)

    def add_tool(self, content: str, **kwargs: Any) -> MemoryEntry:
        """Convenience method to add a tool result message."""
        return self.add(MemoryRole.TOOL.value, content, **kwargs)

    # ---- Retrieval Methods ----

    def get_recent(
        self,
        max_entries: Optional[int] = None,
        roles: Optional[List[str]] = None,
    ) -> List[MemoryEntry]:
        """
        Get recent memory entries.

        Args:
            max_entries: Maximum number of entries to return. Defaults to the
                configured max_turns * 2 (each turn is user + assistant).
            roles: Optional filter to only include specific roles.

        Returns:
            List of MemoryEntry instances.
        """
        limit = max_entries or (self._config.max_turns * 2)
        entries = list(self._entries)

        if roles:
            entries = [e for e in entries if e.role in roles]

        return entries[-limit:]

    def get_messages(
        self,
        max_entries: Optional[int] = None,
        roles: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """
        Get recent entries as message dicts for LLM APIs.

        Args:
            max_entries: Maximum number of messages.
            roles: Optional role filter.

        Returns:
            List of dicts with 'role' and 'content' keys.
        """
        entries = self.get_recent(max_entries=max_entries, roles=roles)
        return [e.to_message() for e in entries]

    def get_all(self) -> List[MemoryEntry]:
        """Get all short-term memory entries."""
        return list(self._entries)

    def get_context(self, include_long_term: bool = True) -> str:
        """
        Get the full conversation context as a string.

        Includes long-term summaries if available and requested.

        Args:
            include_long_term: Whether to include long-term summaries.

        Returns:
            A formatted string of the conversation context.
        """
        parts: List[str] = []

        # Add long-term summaries
        if include_long_term and self._long_term_summaries:
            parts.append("[Previous conversation summary]")
            for summary in self._long_term_summaries:
                parts.append(summary.content)
            parts.append("[End of summary]")

        # Add short-term entries
        for entry in self._entries:
            parts.append(f"{entry.role}: {entry.content}")

        return "\n".join(parts)

    def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> List[MemoryEntry]:
        """
        Simple keyword search through memory entries.

        Performs a case-insensitive substring search.

        Args:
            query: The search query.
            max_results: Maximum number of results.

        Returns:
            List of matching MemoryEntry instances, most recent first.
        """
        query_lower = query.lower()
        results: List[MemoryEntry] = []

        for entry in reversed(self._entries):
            if query_lower in entry.content.lower():
                results.append(entry)
                if len(results) >= max_results:
                    break

        return results

    # ---- Long-Term Memory ----

    async def summarize_older_entries(self) -> Optional[MemorySummary]:
        """
        Create a summary of older entries and move them to long-term storage.

        Entries beyond the summary interval are summarized and removed from
        short-term memory.

        Returns:
            A MemorySummary if entries were summarized, else None.
        """
        if not self._config.enable_long_term:
            return None

        entries_to_summarize = self._entries[:-self._config.long_term_summary_interval * 2]

        if not entries_to_summarize:
            return None

        # Create a text representation of entries to summarize
        text_parts = []
        for entry in entries_to_summarize:
            text_parts.append(f"{entry.role}: {entry.content}")
        text = "\n".join(text_parts)

        # Estimate token count for summary
        summary_tokens = max(1, len(text) // 16)  # Rough compression

        summary = MemorySummary(
            content=f"[Summarized {len(entries_to_summarize)} previous messages]",
            entry_count=len(entries_to_summarize),
            token_count=summary_tokens,
            covered_turns=len(entries_to_summarize) // 2,
        )

        # In production, this would call an LLM to generate a real summary:
        # summary = await self._generate_summary(text)

        self._long_term_summaries.append(summary)

        # Remove summarized entries from short-term memory
        removed_tokens = sum(e.token_count for e in entries_to_summarize)
        self._entries = self._entries[len(entries_to_summarize):]
        self._total_tokens -= removed_tokens
        self._total_tokens = max(0, self._total_tokens)

        return summary

    async def _generate_summary(self, text: str) -> str:
        """
        Generate a summary using the AI module.

        In production, this calls an LLM. For now, returns a placeholder.
        """
        return f"[Summary of {len(text)} characters of previous conversation]"

    def get_long_term_summaries(self) -> List[MemorySummary]:
        """Get all long-term summaries."""
        return list(self._long_term_summaries)

    # ---- Management ----

    def clear(self) -> None:
        """Clear all short-term memory entries."""
        self._entries.clear()
        self._total_tokens = 0

    def clear_long_term(self) -> None:
        """Clear all long-term memory summaries."""
        self._long_term_summaries.clear()

    def clear_all(self) -> None:
        """Clear both short-term and long-term memory."""
        self.clear()
        self.clear_long_term()

    def remove_entry(self, entry_id: str) -> bool:
        """
        Remove a specific entry by ID.

        Args:
            entry_id: The ID of the entry to remove.

        Returns:
            True if the entry was found and removed, False otherwise.
        """
        for i, entry in enumerate(self._entries):
            if entry.id == entry_id:
                self._total_tokens -= entry.token_count
                self._total_tokens = max(0, self._total_tokens)
                self._entries.pop(i)
                return True
        return False

    def export(self) -> Dict[str, Any]:
        """
        Export the full memory state.

        Returns:
            A dict with entries and summaries.
        """
        return {
            "short_term": [e.to_dict() for e in self._entries],
            "long_term": [
                {
                    "id": s.id,
                    "content": s.content,
                    "entry_count": s.entry_count,
                    "timestamp": s.timestamp,
                    "token_count": s.token_count,
                    "covered_turns": s.covered_turns,
                }
                for s in self._long_term_summaries
            ],
            "stats": {
                "entry_count": len(self._entries),
                "total_tokens": self._total_tokens,
                "summary_count": len(self._long_term_summaries),
            },
        }

    def import_memory(self, data: Dict[str, Any]) -> None:
        """
        Import memory from an exported state.

        Args:
            data: The exported memory data.
        """
        self.clear_all()

        for entry_data in data.get("short_term", []):
            entry = MemoryEntry.from_dict(entry_data)
            self._entries.append(entry)
            self._total_tokens += entry.token_count

        for summary_data in data.get("long_term", []):
            self._long_term_summaries.append(MemorySummary(**summary_data))

    def _trim_if_needed(self) -> None:
        """Trim memory to stay within configured limits."""
        # Trim by turn count
        max_entries = self._config.max_turns * 2
        while len(self._entries) > max_entries:
            removed = self._entries.pop(0)
            self._total_tokens -= removed.token_count

        # Trim by token count
        while self._total_tokens > self._config.max_tokens and self._entries:
            removed = self._entries.pop(0)
            self._total_tokens -= removed.token_count

        self._total_tokens = max(0, self._total_tokens)

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return (
            f"ConversationMemory(entries={len(self._entries)}, "
            f"tokens={self._total_tokens}, "
            f"summaries={len(self._long_term_summaries)})"
        )
