"""Claude Code adapter.

Reads session artifacts from ``~/.claude/``:
- ``projects/{path-encoded-name}/*.jsonl`` — per-session transcripts
- ``sessions/{pid}.json`` — process-level metadata

JSONL line types: user, assistant, ai-title, file-history-snapshot.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from briefbridge.adapters.base import (
    BaseAdapter,
    RawCommand,
    RawMessage,
    RawSession,
    RawSessionData,
    RawToolResult,
    SessionFilter,
)
from briefbridge.models.enums import Provider

log = logging.getLogger(__name__)


def _decode_project_dir(dirname: str) -> str:
    """Decode a path-encoded directory name back to a real path.

    Claude Code encodes project paths like ``c--Users--User--Desktop``
    representing ``c:\\Users\\User\\Desktop`` (Windows) or
    ``-home--user--project`` representing ``/home/user/project``.
    Single hyphens within a component are preserved as-is.
    """
    # Claude uses -- as the path separator
    parts = dirname.split("--")
    if not parts:
        return dirname

    # Detect Windows-style: first part is a drive letter (single char)
    first = parts[0]
    if len(first) == 1 and first.isalpha():
        drive = first.upper()
        rest = "\\".join(parts[1:])
        return f"{drive}:\\{rest}"

    # Unix-style: leading "-" in the original becomes an empty first part after split
    # e.g. "-home--user" -> ["", "home", "user"] when split by "--" won't work
    # Actually "-home--user" -> ["-home", "user"] — the leading - encodes /
    if first.startswith("-"):
        # Strip the leading - that represents /
        parts[0] = first[1:]
        return "/" + "/".join(p for p in parts if p)

    return "/".join(parts)


class ClaudeAdapter(BaseAdapter):
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    @property
    def provider_name(self) -> Provider:
        return "claude"

    def is_available(self) -> bool:
        return self.base_path.exists() and (self.base_path / "projects").exists()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_sessions(self, filters: SessionFilter | None = None) -> list[RawSession]:
        sessions: list[RawSession] = []
        projects_dir = self.base_path / "projects"
        if not projects_dir.exists():
            return []

        process_meta = self._load_process_metadata()

        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            project_path = _decode_project_dir(project_dir.name)
            for jsonl_file in sorted(project_dir.glob("*.jsonl")):
                session_id = jsonl_file.stem
                title, started_at, branch = self._peek_session(jsonl_file)

                # Merge process-level metadata if available
                proc = process_meta.get(session_id, {})
                if not started_at and proc.get("startedAt"):
                    started_at = _parse_ts(proc["startedAt"])
                if not branch:
                    branch = proc.get("gitBranch")

                sessions.append(
                    RawSession(
                        id=f"claude:{session_id}",
                        provider="claude",
                        started_at=started_at,
                        repo_path=proc.get("cwd") or project_path,
                        branch=branch,
                        title_hint=title,
                        source_path=str(jsonl_file),
                    )
                )

        return self._apply_filters(sessions, filters)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_session(self, session_id: str) -> RawSessionData:
        native_id = session_id.removeprefix("claude:")
        jsonl_file = self._find_session_file(native_id)
        if jsonl_file is None:
            raise FileNotFoundError(f"Session file not found for {session_id}")

        messages: list[RawMessage] = []
        commands: list[RawCommand] = []
        tool_results: list[RawToolResult] = []
        metadata: dict = {}
        raw_lines: list[dict] = []
        title: str | None = None
        branch: str | None = None
        repo_path: str | None = None
        started_at: datetime | None = None
        ended_at: datetime | None = None
        files_touched: list[str] = []

        for line in jsonl_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            raw_lines.append(entry)
            entry_type = entry.get("type", "")

            if entry_type == "user":
                ts = _parse_ts(entry.get("timestamp"))
                started_at = started_at or ts
                ended_at = ts or ended_at
                branch = branch or entry.get("gitBranch")
                repo_path = repo_path or entry.get("cwd")

                text = _extract_message_text(entry.get("message", {}))
                messages.append(
                    RawMessage(role="user", text=text, timestamp=ts, metadata=entry)
                )

            elif entry_type == "assistant":
                ts = _parse_ts(entry.get("timestamp"))
                ended_at = ts or ended_at
                msg = entry.get("message", {})
                text_parts: list[str] = []

                for block in msg.get("content", []):
                    if isinstance(block, str):
                        text_parts.append(block)
                    elif isinstance(block, dict):
                        btype = block.get("type", "")
                        if btype == "text":
                            text_parts.append(block.get("text", ""))
                        elif btype == "tool_use":
                            tool_results.append(
                                RawToolResult(
                                    tool_name=block.get("name", ""),
                                    result=json.dumps(block.get("input", {})),
                                    timestamp=ts,
                                    metadata=block,
                                )
                            )
                            # Extract file refs from tool inputs
                            inp = block.get("input", {})
                            if isinstance(inp, dict):
                                for v in inp.values():
                                    if isinstance(v, str) and ("/" in v or "\\" in v):
                                        if v not in files_touched:
                                            files_touched.append(v)

                messages.append(
                    RawMessage(
                        role="assistant",
                        text="\n".join(text_parts),
                        timestamp=ts,
                        metadata=entry,
                    )
                )
                # Extract commands from tool_use blocks
                for block in msg.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        if block.get("name") in ("bash", "execute_command", "terminal"):
                            inp = block.get("input", {})
                            cmd = inp.get("command", inp.get("cmd", ""))
                            if cmd:
                                commands.append(
                                    RawCommand(command=cmd, timestamp=ts)
                                )

            elif entry_type == "ai-title":
                title = entry.get("aiTitle", entry.get("title", title))

            elif entry_type == "tool_result":
                # Some Claude sessions include tool_result entries
                ts = _parse_ts(entry.get("timestamp"))
                tool_results.append(
                    RawToolResult(
                        tool_name=entry.get("tool_name", ""),
                        result=entry.get("output", ""),
                        status=entry.get("status", ""),
                        timestamp=ts,
                        metadata=entry,
                    )
                )

        session = RawSession(
            id=session_id,
            provider="claude",
            started_at=started_at,
            ended_at=ended_at,
            repo_path=repo_path,
            branch=branch,
            title_hint=title,
            files_touched=files_touched,
            source_path=str(jsonl_file),
        )
        return RawSessionData(
            session=session,
            messages=messages,
            commands=commands,
            tool_results=tool_results,
            metadata=metadata,
            raw_lines=raw_lines,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_process_metadata(self) -> dict[str, dict]:
        """Load all sessions/*.json process metadata keyed by sessionId."""
        meta: dict[str, dict] = {}
        sessions_dir = self.base_path / "sessions"
        if not sessions_dir.exists():
            return meta
        for f in sessions_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sid = data.get("sessionId", "")
                if sid:
                    meta[sid] = data
            except (json.JSONDecodeError, OSError):
                continue
        return meta

    def _find_session_file(self, native_id: str) -> Path | None:
        projects_dir = self.base_path / "projects"
        if not projects_dir.exists():
            return None
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            candidate = project_dir / f"{native_id}.jsonl"
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _peek_session(path: Path) -> tuple[str | None, datetime | None, str | None]:
        """Extract title, first timestamp, and branch from a session file."""
        title: str | None = None
        ts: datetime | None = None
        branch: str | None = None
        try:
            with path.open(encoding="utf-8") as f:
                for i, raw in enumerate(f):
                    if i > 50:
                        break  # only scan first lines
                    raw = raw.strip()
                    if not raw:
                        continue
                    entry = json.loads(raw)
                    etype = entry.get("type", "")
                    if etype == "ai-title":
                        title = entry.get("aiTitle", entry.get("title"))
                    if etype == "user" and ts is None:
                        ts = _parse_ts(entry.get("timestamp"))
                        branch = branch or entry.get("gitBranch")
        except (json.JSONDecodeError, OSError):
            pass
        return title, ts, branch

    @staticmethod
    def _apply_filters(
        sessions: list[RawSession], filters: SessionFilter | None
    ) -> list[RawSession]:
        if not filters:
            return sessions
        result = sessions
        if filters.last_hours is not None:
            cutoff = datetime.now(tz=timezone.utc).timestamp() - filters.last_hours * 3600
            result = [
                s
                for s in result
                if s.started_at and s.started_at.timestamp() >= cutoff
            ]
        if filters.repo:
            result = [s for s in result if s.repo_path and filters.repo in s.repo_path]
        if filters.branch:
            result = [s for s in result if s.branch and filters.branch in s.branch]
        return result


def _extract_message_text(msg: dict) -> str:
    content = msg.get("content", [])
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
    return "\n".join(parts)


def _parse_ts(value: str | int | float | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            # Claude uses millisecond epoch timestamps
            if value > 1e12:
                value = value / 1000
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, ValueError):
            return None
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None
