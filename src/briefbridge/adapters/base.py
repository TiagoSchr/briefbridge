"""Abstract base adapter and raw data structures for session ingestion."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from briefbridge.models.enums import Provider


@dataclass
class RawMessage:
    role: str  # "user", "assistant", "system", "developer"
    text: str
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawCommand:
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timestamp: datetime | None = None
    duration_ms: int | None = None


@dataclass
class RawToolResult:
    tool_name: str
    result: str = ""
    status: str = ""
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawSession:
    """Lightweight session metadata for listing."""

    id: str
    provider: Provider
    started_at: datetime | None = None
    ended_at: datetime | None = None
    repo_path: str | None = None
    branch: str | None = None
    title_hint: str | None = None
    files_touched: list[str] = field(default_factory=list)
    source_path: str = ""


@dataclass
class RawSessionData:
    """Full parsed session data for extraction."""

    session: RawSession
    messages: list[RawMessage] = field(default_factory=list)
    commands: list[RawCommand] = field(default_factory=list)
    tool_results: list[RawToolResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_lines: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SessionFilter:
    last_hours: float | None = None
    repo: str | None = None
    branch: str | None = None
    provider: Provider | None = None


class BaseAdapter(abc.ABC):
    """Abstract base class for provider adapters."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> Provider: ...

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider's local data is accessible."""
        ...

    @abc.abstractmethod
    def discover_sessions(self, filters: SessionFilter | None = None) -> list[RawSession]:
        """List sessions matching the given filters."""
        ...

    @abc.abstractmethod
    def read_session(self, session_id: str) -> RawSessionData:
        """Read and parse full session data."""
        ...
