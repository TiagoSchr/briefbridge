"""Platform-aware configuration and provider path detection."""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


def _default_codex_path() -> Path:
    return Path.home() / ".codex"


def _default_claude_path() -> Path:
    return Path.home() / ".claude"


def _default_copilot_path() -> Path:
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "Code" / "User" / "workspaceStorage"
    return Path.home() / ".config" / "Code" / "User" / "workspaceStorage"


def _default_data_dir() -> Path:
    if platform.system() == "Windows":
        appdata = os.environ.get("LOCALAPPDATA", os.environ.get("APPDATA", ""))
        if appdata:
            return Path(appdata) / "briefbridge"
    return Path.home() / ".config" / "briefbridge"


def detect_repo_root() -> str | None:
    """Detect the git repository root from cwd."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


@dataclass
class BriefBridgeConfig:
    codex_path: Path = field(default_factory=_default_codex_path)
    claude_path: Path = field(default_factory=_default_claude_path)
    copilot_path: Path = field(default_factory=_default_copilot_path)
    data_dir: Path = field(default_factory=_default_data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "briefbridge.db"

    def ensure_data_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls) -> BriefBridgeConfig:
        """Load config with env-var overrides."""
        kwargs: dict = {}
        if v := os.environ.get("BRIEFBRIDGE_CODEX_PATH"):
            kwargs["codex_path"] = Path(v)
        if v := os.environ.get("BRIEFBRIDGE_CLAUDE_PATH"):
            kwargs["claude_path"] = Path(v)
        if v := os.environ.get("BRIEFBRIDGE_COPILOT_PATH"):
            kwargs["copilot_path"] = Path(v)
        if v := os.environ.get("BRIEFBRIDGE_DATA_DIR"):
            kwargs["data_dir"] = Path(v)
        return cls(**kwargs)
