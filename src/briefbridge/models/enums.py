"""Enumerations and literal types used across BriefBridge."""

from __future__ import annotations

from enum import Enum
from typing import Literal

Provider = Literal["codex", "claude", "copilot", "unknown"]

ConfidenceLevel = Literal["high", "medium", "low"]

PriorityLevel = Literal["high", "medium", "low"]


class ImportMode(str, Enum):
    """Selective import modes for the `use` command."""

    SUMMARY = "summary"
    GOAL = "goal"
    HYPOTHESIS = "hypothesis"
    FILES = "files"
    ERRORS = "errors"
    COMMANDS = "commands"
    DECISIONS = "decisions"
    TODOS = "todos"
    COMPACT = "compact"
    FULL = "full"
