"""BriefBridge MCP Server — single backend for Copilot, Claude Code, and Codex."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from briefbridge.config import BriefBridgeConfig
from briefbridge.models.enums import ImportMode, Provider
from briefbridge.services.handoff import HandoffService
from briefbridge.services.search import SearchService
from briefbridge.services.sessions import SessionsService
from briefbridge.storage.sqlite import StorageBackend

mcp = FastMCP(
    "BriefBridge",
    instructions="Cross-agent session handoff — list, inspect, pack, use, and search coding sessions.",
)

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_config: BriefBridgeConfig | None = None
_storage: StorageBackend | None = None


def _get_config() -> BriefBridgeConfig:
    global _config
    if _config is None:
        _config = BriefBridgeConfig.load()
    return _config


def _get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        cfg = _get_config()
        cfg.ensure_data_dir()
        _storage = StorageBackend(cfg.db_path)
    return _storage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_PROVIDERS = {"any", "copilot", "claude", "codex"}


def _resolve_provider(raw: str | None) -> Provider | None:
    """Normalize provider string. Returns None for 'any' or empty."""
    if not raw or raw == "any":
        return None
    val = raw.lower().strip()
    if val in ("copilot", "claude", "codex"):
        return val  # type: ignore[return-value]
    return None


def _session_status(s: Any) -> str:
    """Infer session status from timestamps."""
    started = getattr(s, "started_at", None) or (s.get("started_at") if isinstance(s, dict) else None)
    ended = getattr(s, "ended_at", None) or (s.get("ended_at") if isinstance(s, dict) else None)
    if ended:
        return "finished"
    if started:
        return "active"
    return "unknown"


def _iso(dt: datetime | str | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def bb_sessions_list(
    hours: float = 24,
    repo: str | None = None,
    provider: str = "any",
) -> dict:
    """List recent coding sessions across all providers.

    Args:
        hours: How many hours back to look (default 24).
        repo: Repository filter — "auto" to detect from cwd, a path string, or null for all.
        provider: Filter by provider: "any", "copilot", "claude", or "codex".
    """
    prov = _resolve_provider(provider)
    svc = SessionsService(config=_get_config(), storage=_get_storage())

    results = svc.list_sessions(
        last_hours=hours if hours > 0 else None,
        repo=repo if repo and repo != "null" else None,
        provider=prov,
    )

    sessions = []
    for s in results:
        sessions.append({
            "id": s.id,
            "provider": s.provider,
            "time": s.started_at,
            "repo": s.repo_name,
            "files_count": len(s.files_touched) if s.files_touched else 0,
            "title": s.title,
            "status": _session_status(s),
        })

    return {"sessions": sessions}


@mcp.tool()
def bb_session_inspect(session_id: str) -> dict:
    """Inspect a specific session — show objective, files, errors, commands, decisions, and pending items.

    Args:
        session_id: The session identifier (e.g. "claude:abc123", "copilot:xyz").
    """
    svc = HandoffService(config=_get_config(), storage=_get_storage())

    try:
        pack = svc.get_or_generate(session_id)
    except FileNotFoundError:
        return {"error": f"Session not found: {session_id}"}

    return {
        "id": pack.source_session_id,
        "provider": pack.source_provider,
        "repo": pack.repo_name,
        "branch": pack.branch,
        "objective": pack.objective,
        "main_hypothesis": pack.main_hypothesis,
        "relevant_files": [
            {"path": f.path, "role": f.role, "changed": f.changed}
            for f in pack.relevant_files
        ],
        "errors_found": [
            {"summary": e.summary, "source": e.source}
            for e in pack.errors_found
        ],
        "important_commands": [
            {"command": c.command, "exit_code": c.exit_code, "summary": c.summary}
            for c in pack.important_commands
        ],
        "decisions_made": [
            {"text": d.text, "confidence": d.confidence}
            for d in pack.decisions_made
        ],
        "pending_items": [
            {"text": p.text, "priority": p.priority}
            for p in pack.pending_items
        ],
    }


@mcp.tool()
def bb_session_pack(
    session_id: str,
    mode: str = "compact",
) -> dict:
    """Generate a handoff pack for a session.

    Args:
        session_id: The session identifier.
        mode: Output mode — "summary", "compact", or "full".
    """
    svc = HandoffService(config=_get_config(), storage=_get_storage())

    try:
        pack = svc.get_or_generate(session_id)
    except FileNotFoundError:
        return {"error": f"Session not found: {session_id}"}

    from briefbridge.render.json_export import render_json
    from briefbridge.render.markdown import render_markdown
    from briefbridge.render.plain_text import render_plain

    # Map mode to ImportMode for plain text
    mode_lower = mode.lower().strip()
    try:
        import_mode = ImportMode(mode_lower)
    except ValueError:
        import_mode = ImportMode.COMPACT

    return {
        "handoff_id": pack.handoff_id,
        "markdown": render_markdown(pack),
        "plain_text": render_plain(pack, import_mode),
        "json": json.loads(render_json(pack)),
    }


@mcp.tool()
def bb_session_use(
    session_id: str,
    mode: str = "compact",
) -> dict:
    """Generate a context block ready to paste into another agent.

    Args:
        session_id: The session identifier.
        mode: Import mode — one of: summary, goal, hypothesis, files, errors,
              commands, decisions, todos, compact, full.
    """
    svc = HandoffService(config=_get_config(), storage=_get_storage())

    # Parse comma-separated modes
    mode_names = [m.strip().lower() for m in mode.split(",")]
    modes: list[ImportMode] = []
    for name in mode_names:
        try:
            modes.append(ImportMode(name))
        except ValueError:
            pass

    if not modes:
        modes = [ImportMode.COMPACT]

    try:
        output = svc.use_pack(session_id, modes)
    except FileNotFoundError:
        return {"error": f"Session not found: {session_id}"}

    return {"context_block": output}


@mcp.tool()
def bb_session_search(
    query: str,
    hours: float = 72,
    provider: str = "any",
    repo: str | None = None,
) -> dict:
    """Search across sessions for a keyword or topic.

    Args:
        query: Search query string.
        hours: How many hours back to search (default 72).
        provider: Filter by provider: "any", "copilot", "claude", or "codex".
        repo: Repository filter — "auto", a path, or null.
    """
    storage = _get_storage()
    config = _get_config()

    # First ensure sessions are indexed
    prov = _resolve_provider(provider)
    sessions_svc = SessionsService(config=config, storage=storage)
    sessions_svc.list_sessions(
        last_hours=hours if hours > 0 else None,
        repo=repo if repo and repo != "null" else None,
        provider=prov,
    )

    # Now search using FTS
    search_svc = SearchService(config=config, storage=storage)
    results = storage.search(query)

    matches = []
    for r in results:
        matches.append({
            "session_id": r.session_id,
            "provider": "",  # FTS results don't carry provider directly
            "score": r.rank,
            "snippet": r.snippet,
        })

    return {"matches": matches}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the MCP server via STDIO transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
