"""Canonical HandoffPack schema and all sub-models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from briefbridge.models.enums import ConfidenceLevel, PriorityLevel, Provider


class RelevantFile(BaseModel):
    path: str
    role: str = ""
    changed: bool = False
    referenced_count: int | None = None


class SessionError(BaseModel):
    summary: str
    raw_excerpt: str = ""
    source: str = ""
    timestamp: datetime | None = None


class SessionCommand(BaseModel):
    command: str
    exit_code: int | None = None
    summary: str = ""
    timestamp: datetime | None = None


class DecisionItem(BaseModel):
    text: str
    confidence: ConfidenceLevel = "medium"


class PendingItem(BaseModel):
    text: str
    priority: PriorityLevel = "medium"


class ConfidenceReport(BaseModel):
    objective: ConfidenceLevel = "low"
    main_hypothesis: ConfidenceLevel = "low"
    decisions_made: ConfidenceLevel = "low"
    pending_items: ConfidenceLevel = "low"


class RawSourcePointer(BaseModel):
    provider: Provider
    local_path: str
    kind: str = ""


class HandoffPack(BaseModel):
    handoff_id: str
    source_provider: Provider
    source_session_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    session_started_at: datetime | None = None
    session_ended_at: datetime | None = None
    repo_path: str | None = None
    repo_name: str | None = None
    branch: str | None = None
    commit_head: str | None = None
    title: str | None = None
    objective: str | None = None
    main_hypothesis: str | None = None
    relevant_files: list[RelevantFile] = Field(default_factory=list)
    errors_found: list[SessionError] = Field(default_factory=list)
    important_commands: list[SessionCommand] = Field(default_factory=list)
    decisions_made: list[DecisionItem] = Field(default_factory=list)
    pending_items: list[PendingItem] = Field(default_factory=list)
    confidence: ConfidenceReport = Field(default_factory=ConfidenceReport)
    raw_sources: list[RawSourcePointer] = Field(default_factory=list)
