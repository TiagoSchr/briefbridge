"""Codex wrapper — installs a BriefBridge skill for OpenAI Codex.

Codex uses the Agent Skills standard (https://developers.openai.com/codex/skills).
Skills live in ~/.agents/skills/<name>/ and contain a SKILL.md file.
Invoke the installed skill by typing `$briefbridge` in Codex.

Usage:
    bb wrapper install --client codex
    bb wrapper uninstall --client codex
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

# The user-level skill directory per the Codex skills spec.
# Codex reads skills from $HOME/.agents/skills at startup.
_SKILL_NAME = "briefbridge"


def _resolve_bb_cmd() -> str:
    """Return the most reliable way to invoke bb in a restricted shell.

    Tries (in order):
    1. Full absolute path to bb.exe / bb if on PATH
    2. `python -m briefbridge` using the current interpreter
    """
    bb = shutil.which("bb") or shutil.which("bb.exe")
    if bb:
        # Normalise to forward slashes for cross-platform readability,
        # but keep the absolute path so the sandbox finds it.
        return str(Path(bb))
    # Fallback: use the current Python interpreter
    return f'"{sys.executable}" -m briefbridge'


def _build_skill_md(bb_cmd: str) -> str:
    return f"""\
---
name: briefbridge
description: Cross-agent session handoff tool. Use this skill ONLY when the user \
asks about previous coding sessions, wants to see past work, needs a summary of a \
past session, or wants to continue work started in a different tool. \
NEVER read source code files or explore the repository to answer — always run the \
bb CLI command instead. Do NOT use for general coding questions.
---

# BriefBridge — Cross-Agent Session Handoff

## IMPORTANT: Always run the CLI — do not read files

When this skill is active, answer ALL questions by running the `bb` command below.
**Do not** read source files, explore the project directory, or run `git status`.
The bb tool handles everything internally.

## bb command (absolute path — works inside sandbox)

```
{bb_cmd}
```

## Answering common questions

| User says | Run this |
|-----------|----------|
| "funcionando?" / "is it working?" | `{bb_cmd} sessions --last 24h` |
| "list sessions" / "show sessions" | `{bb_cmd} sessions --last 24h` |
| "show copilot sessions" | `{bb_cmd} sessions --provider copilot` |
| "inspect <id>" | `{bb_cmd} inspect <id> --json` |
| "pack <id>" / "handoff <id>" | `{bb_cmd} pack <id>` |
| "use <id>" / "context for <id>" | `{bb_cmd} use <id> --mode compact` |
| "search <query>" | `{bb_cmd} sessions --json` then match |

## All available commands

```bash
{bb_cmd} sessions --last 24h
{bb_cmd} sessions --provider copilot   # or claude / codex
{bb_cmd} inspect <session_id> --json
{bb_cmd} pack <session_id>
{bb_cmd} use <session_id> --mode compact
{bb_cmd} ask <session_id> "<question>"
{bb_cmd} export <session_id> --format md
```

## Session ID format

Run `{bb_cmd} sessions --json` to list IDs.
Format: `copilot:abc123`, `claude:def456`, `codex:789abc`

## Context modes for `use`

`compact` (default), `full`, `goal`, `files`, `errors`, `commands`, `decisions`, `todos`
Combine: `--mode goal,files,errors`

## MCP tools (if bb-mcp is in config.toml)

- `bb_sessions_list` — list sessions
- `bb_session_inspect` — full extraction
- `bb_session_pack` — handoff pack
- `bb_session_use` — paste-ready block
- `bb_session_search` — FTS search
"""

_OPENAI_YAML = """\
interface:
  display_name: "BriefBridge"
  short_description: "Cross-agent session handoff — list, inspect, and continue past sessions"
  default_prompt: "Run bb sessions --last 24h and show the results. Do not read any source files."

policy:
  allow_implicit_invocation: true
"""


def _agents_skills_dir() -> Path:
    """User-level skills directory per Codex skills spec."""
    return Path.home() / ".agents" / "skills"


def install(skills_dir: Path | None = None, verbose: bool = True) -> list[Path]:
    """Install the BriefBridge skill into ~/.agents/skills/briefbridge/."""
    base = skills_dir or _agents_skills_dir()
    skill_dir = base / _SKILL_NAME
    agents_dir = skill_dir / "agents"
    skill_dir.mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)

    bb_cmd = _resolve_bb_cmd()
    installed: list[Path] = []

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(_build_skill_md(bb_cmd), encoding="utf-8")
    installed.append(skill_md)
    if verbose:
        print(f"  ok {skill_md}")
        print(f"    bb command: {bb_cmd}")

    openai_yaml = agents_dir / "openai.yaml"
    openai_yaml.write_text(_OPENAI_YAML, encoding="utf-8")
    installed.append(openai_yaml)
    if verbose:
        print(f"  ok {openai_yaml}")

    if verbose:
        print(f"\n  Invoke in Codex by typing: $briefbridge")
        print(f"  Or let Codex pick it automatically when you ask about sessions.\n")

    return installed


def uninstall(skills_dir: Path | None = None, verbose: bool = True) -> None:
    """Remove the BriefBridge skill from ~/.agents/skills/briefbridge/."""
    import shutil

    base = skills_dir or _agents_skills_dir()
    skill_dir = base / _SKILL_NAME

    if skill_dir.exists():
        shutil.rmtree(skill_dir)
        if verbose:
            print(f"  removed {skill_dir}")
    elif verbose:
        print(f"  (nothing to remove — {skill_dir} not found)")


def list_commands() -> list[str]:
    """Return the skill name (single skill replaces the old per-command files)."""
    return [_SKILL_NAME]


def get_mcp_config() -> dict:
    """Return MCP server config block for ~/.codex/config.toml."""
    return {
        "mcp_servers": {
            "briefbridge": {
                "command": "bb-mcp",
                "args": [],
            }
        }
    }


def print_mcp_config() -> None:
    print(json.dumps(get_mcp_config(), indent=2))
