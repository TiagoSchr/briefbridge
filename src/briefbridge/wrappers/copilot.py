"""Copilot wrapper — VS Code extension helper for MCP-backed @bb participant.

This module handles configuration generation and MCP client integration
for the VS Code extension. The actual UX code lives in vscode-ext/.
"""

from __future__ import annotations

import json
from pathlib import Path


def get_mcp_config() -> dict:
    """Return MCP server config block for VS Code settings.json / GitHub Copilot."""
    return {
        "briefbridge": {
            "command": "bb-mcp",
            "args": [],
            "type": "stdio",
        }
    }


def get_vscode_settings_fragment() -> dict:
    """Return VS Code settings.json fragment to enable MCP for Copilot."""
    return {
        "github.copilot.chat.experimental.mcp": {
            "servers": get_mcp_config()
        }
    }


def print_vscode_settings() -> None:
    """Print the VS Code settings fragment to add for MCP integration."""
    print(json.dumps(get_vscode_settings_fragment(), indent=2))


def get_extension_config_schema() -> dict:
    """Return the VS Code extension contributes.configuration schema fragment."""
    return {
        "title": "BriefBridge",
        "properties": {
            "briefbridge.bbPath": {
                "type": "string",
                "default": "bb",
                "description": "Path to the `bb` CLI executable. Defaults to 'bb' (assumes it is on PATH).",
            },
            "briefbridge.defaultProvider": {
                "type": "string",
                "enum": ["any", "copilot", "claude", "codex"],
                "default": "any",
                "description": "Default provider to list sessions from.",
            },
            "briefbridge.defaultHours": {
                "type": "number",
                "default": 24,
                "description": "Default time window (in hours) for session listing.",
            },
        },
    }


def install_mcp_config(settings_path: Path | None = None, verbose: bool = True) -> Path:
    """Inject MCP server config into VS Code settings.json.

    Args:
        settings_path: Path to settings.json. Defaults to global VS Code user settings.
    """
    import platform

    if settings_path is None:
        if platform.system() == "Windows":
            settings_path = Path.home() / "AppData" / "Roaming" / "Code" / "User" / "settings.json"
        elif platform.system() == "Darwin":
            settings_path = Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
        else:
            settings_path = Path.home() / ".config" / "Code" / "User" / "settings.json"

    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    # Merge MCP server config
    mcp_key = "github.copilot.chat.experimental.mcp"
    if mcp_key not in existing:
        existing[mcp_key] = {"servers": {}}
    if "servers" not in existing[mcp_key]:
        existing[mcp_key]["servers"] = {}

    existing[mcp_key]["servers"]["briefbridge"] = get_mcp_config()["briefbridge"]

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    if verbose:
        print(f"  ok MCP config added to {settings_path}")

    return settings_path
