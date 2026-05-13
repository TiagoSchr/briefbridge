"""Claude Code wrapper — generates slash command files for /bb: commands.

Run once to install the custom slash commands into Claude Code:

    python -m briefbridge.wrappers.claude install

Or use the bb CLI:

    bb wrapper install --client claude
"""

from __future__ import annotations

import json
from pathlib import Path

# Slash command definitions
# Claude Code reads custom commands from ~/.claude/commands/*.md
_COMMANDS: dict[str, dict] = {
    "bb:sessions": {
        "description": "Lista sessões recentes de todas as ferramentas. Uso: /bb:sessions [codex|claude|copilot]",
        "prompt": """\
!bb sessions --last 7d $ARGUMENTS 2>/dev/null
""",
    },
    "bb:inspect": {
        "description": "Inspect a BriefBridge session — show objective, files, errors, and decisions.",
        "prompt": """\
Inspect a BriefBridge session.

Run: `bb inspect $SESSION_ID --json`

Then format the result showing:
1. Session metadata (provider, repo, branch, time)
2. Objective (if inferred)
3. Relevant files touched
4. Errors found
5. Important commands run
6. Decisions made
7. Pending items

If no session ID was provided, first run `bb sessions --json --last 24h` to list recent sessions and let the user pick one.
""",
    },
    "bb:pack": {
        "description": "Generate a full handoff pack for a BriefBridge session.",
        "prompt": """\
Generate a handoff pack for a BriefBridge session.

Run: `bb pack $SESSION_ID --json`

Then present the pack as a structured Markdown report with sections:
- Objective
- Hypothesis
- Relevant Files
- Errors Found
- Important Commands
- Decisions Made
- Pending Items

If no session ID was provided, first run `bb sessions --json --last 24h` and let the user pick one.
""",
    },
    "bb:use": {
        "description": "Injeta o contexto de uma sessão específica direto no chat. Uso: /bb:use <session_id>",
        "prompt": """\
!bb use $ARGUMENTS --mode compact 2>/dev/null || echo "Uso: /bb:use <session_id>  |  Exemplo: /bb:use claude:abc123  |  Liste as sessoes com /bb:sessions"
""",
    },
    "bb:context": {
        "description": "Injeta o contexto da sessão mais recente direto no chat, sem gastar tokens.",
        "prompt": """\
!bb use $(bb sessions --json --last 48h 2>/dev/null | python -c "import json,sys; s=json.load(sys.stdin); print(s[0]['id'] if s else '')" 2>/dev/null) --mode compact 2>/dev/null
""",
    },
    "bb:search": {
        "description": "Search across BriefBridge sessions for a keyword or topic.",
        "prompt": """\
Search across BriefBridge sessions using full-text search.

Run: `bb sessions --json --last 72h` to list recent sessions, then use `bb pack $SESSION_ID --json` to inspect the ones that match the query.

Alternatively run: `bb ask $SESSION_ID "$QUERY"` for targeted search in a specific session.

Format the results showing which sessions matched and what the relevant context was.
""",
    },
}


def _claude_commands_dir() -> Path:
    """Return ~/.claude/commands/bb/ path.

    Claude Code reads ~/.claude/commands/<subdir>/<name>.md and exposes them
    as /<subdir>:<name> slash commands — so this produces /bb:sessions, /bb:inspect, etc.
    """
    return Path.home() / ".claude" / "commands" / "bb"


def install(commands_dir: Path | None = None, verbose: bool = True) -> list[Path]:
    """Install Claude Code slash commands.

    Creates ~/.claude/commands/bb/<name>.md files, invoked as /bb:<name>.
    """
    target = commands_dir or _claude_commands_dir()
    target.mkdir(parents=True, exist_ok=True)

    # Also clean up any old flat files (bb_sessions.md etc.) from previous installs
    old_dir = target.parent
    for old_name in ["bb_sessions", "bb_inspect", "bb_pack", "bb_use", "bb_search"]:
        old_path = old_dir / f"{old_name}.md"
        if old_path.exists():
            old_path.unlink()

    installed: list[Path] = []
    for name, meta in _COMMANDS.items():
        # name is e.g. "bb:sessions" — strip the "bb:" prefix for the filename
        # so the file is bb/sessions.md → /bb:sessions in Claude Code
        filename = name.split(":", 1)[-1] + ".md"
        path = target / filename
        content = f"---\ndescription: {meta['description']}\n---\n\n{meta['prompt'].strip()}\n"
        path.write_text(content, encoding="utf-8")
        installed.append(path)
        if verbose:
            print(f"  ok {path}  ->  /{name}")

    return installed


def uninstall(commands_dir: Path | None = None, verbose: bool = True) -> None:
    """Remove installed Claude Code slash commands."""
    import shutil

    target = commands_dir or _claude_commands_dir()
    if target.exists():
        shutil.rmtree(target)
        if verbose:
            print(f"  removed {target}")


def list_commands() -> list[str]:
    """Return the list of slash command names."""
    return list(_COMMANDS.keys())


def get_mcp_config() -> dict:
    """Return the MCP server config dict for claude_desktop_config.json / .claude settings."""
    return {
        "briefbridge": {
            "command": "bb-mcp",
            "args": [],
            "env": {},
        }
    }


def print_mcp_config() -> None:
    """Print the MCP config block to add to Claude Code settings."""
    config = {"mcpServers": get_mcp_config()}
    print(json.dumps(config, indent=2))
