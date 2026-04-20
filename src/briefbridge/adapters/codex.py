"""OpenAI Codex CLI adapter.

Reads session artifacts from ``~/.codex/``:
- ``session_index.jsonl`` — fast session listing
- ``sessions/YYYY/MM/DD/rollout-*.jsonl`` — full transcripts

JSONL line types: session_meta, event_msg, response_item, turn_context.
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


class CodexAdapter(BaseAdapter):
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    @property
    def provider_name(self) -> Provider:
        return "codex"

    def is_available(self) -> bool:
        return self.base_path.exists()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_sessions(self, filters: SessionFilter | None = None) -> list[RawSession]:
        sessions: list[RawSession] = []

        # Prefer session_index.jsonl for fast listing
        index_path = self.base_path / "session_index.jsonl"
        if index_path.exists():
            sessions = self._discover_from_index(index_path)
        else:
            sessions = self._discover_from_fs()

        return self._apply_filters(sessions, filters)

    def _discover_from_index(self, index_path: Path) -> list[RawSession]:
        sessions: list[RawSession] = []
        for line in index_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = entry.get("id", "")
            updated = entry.get("updated_at")
            ts = _parse_ts(updated) if updated else None
            sessions.append(
                RawSession(
                    id=f"codex:{sid}",
                    provider="codex",
                    started_at=ts,
                    title_hint=entry.get("thread_name"),
                    source_path=str(self.base_path),
                )
            )
        return sessions

    def _discover_from_fs(self) -> list[RawSession]:
        sessions_dir = self.base_path / "sessions"
        if not sessions_dir.exists():
            return []
        result: list[RawSession] = []
        for jsonl_file in sorted(sessions_dir.rglob("*.jsonl")):
            meta = self._peek_session_meta(jsonl_file)
            sid = meta.get("id", jsonl_file.stem)
            ts = _parse_ts(meta.get("timestamp")) if meta.get("timestamp") else None
            result.append(
                RawSession(
                    id=f"codex:{sid}",
                    provider="codex",
                    started_at=ts,
                    repo_path=meta.get("cwd"),
                    source_path=str(jsonl_file),
                )
            )
        return result

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_session(self, session_id: str) -> RawSessionData:
        native_id = session_id.removeprefix("codex:")
        jsonl_file = self._find_session_file(native_id)
        if jsonl_file is None:
            raise FileNotFoundError(f"Session file not found for {session_id}")

        messages: list[RawMessage] = []
        commands: list[RawCommand] = []
        tool_results: list[RawToolResult] = []
        metadata: dict = {}
        raw_lines: list[dict] = []
        repo_path: str | None = None
        branch: str | None = None
        title: str | None = None
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

            # Real Codex wraps data in a "payload" key; support both formats
            payload = entry.get("payload", entry)

            if entry_type == "session_meta":
                metadata.update(payload)
                repo_path = repo_path or payload.get("cwd")
                started_at = started_at or _parse_ts(payload.get("timestamp") or entry.get("timestamp"))
                title = title or payload.get("thread_name")

            elif entry_type == "turn_context":
                repo_path = repo_path or payload.get("cwd")

            elif entry_type == "response_item":
                role = payload.get("role", entry.get("role", "unknown"))
                text_parts: list[str] = []
                for c in (payload.get("content") or entry.get("content") or []):
                    if isinstance(c, dict):
                        text_parts.append(c.get("text", c.get("input_text", "")))
                    elif isinstance(c, str):
                        text_parts.append(c)
                ts = _parse_ts(entry.get("timestamp"))
                ended_at = ts or ended_at
                messages.append(RawMessage(role=role, text="\n".join(text_parts), timestamp=ts))

            elif entry_type == "event_msg":
                event = payload.get("event", payload.get("event_type", payload.get("kind", "")))
                msg_text = payload.get("message", "")
                if event == "exec_command_end" or "command" in payload:
                    cmd = payload.get("command", "")
                    commands.append(
                        RawCommand(
                            command=cmd,
                            stdout=payload.get("stdout", ""),
                            stderr=payload.get("stderr", ""),
                            exit_code=payload.get("exit_code"),
                            timestamp=_parse_ts(entry.get("timestamp")),
                            duration_ms=payload.get("duration"),
                        )
                    )
                    _collect_file_refs(cmd, files_touched)
                elif event == "user_message" and msg_text:
                    # Codex stores the user text also as event_msg with kind=plain
                    ts = _parse_ts(entry.get("timestamp"))
                    ended_at = ts or ended_at
                    messages.append(RawMessage(role="user", text=msg_text, timestamp=ts))

        session = RawSession(
            id=session_id,
            provider="codex",
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

    def _find_session_file(self, native_id: str) -> Path | None:
        sessions_dir = self.base_path / "sessions"
        if not sessions_dir.exists():
            return None
        for f in sessions_dir.rglob("*.jsonl"):
            if native_id in f.stem:
                return f
        # Fallback: try to match by peeking session_meta.id
        for f in sessions_dir.rglob("*.jsonl"):
            meta = self._peek_session_meta(f)
            if meta.get("id") == native_id:
                return f
        return None

    @staticmethod
    def _peek_session_meta(path: Path) -> dict:
        try:
            for line in path.open(encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("type") == "session_meta":
                    payload = entry.get("payload", entry)
                    # Keep the outer timestamp if payload doesn't have one
                    if "timestamp" not in payload and "timestamp" in entry:
                        payload["timestamp"] = entry["timestamp"]
                    return payload
        except (json.JSONDecodeError, OSError):
            pass
        return {}

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


def _parse_ts(value: str | int | float | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
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


def _collect_file_refs(cmd: str, files: list[str]) -> None:
    """Best-effort extraction of file paths from commands."""
    for token in cmd.split():
        if "/" in token or "\\" in token:
            clean = token.strip("'\"")
            if clean and clean not in files:
                files.append(clean)
