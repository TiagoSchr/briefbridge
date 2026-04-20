"""GitHub Copilot Chat adapter.

Reads session artifacts from VS Code workspace storage:
- ``workspaceStorage/{hash}/chatSessions/*.jsonl``

Uses a kind-based incremental JSONL format:
- kind 0 — session metadata
- kind 1 — key-value updates
- kind 2 — request/response data
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


class CopilotAdapter(BaseAdapter):
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    @property
    def provider_name(self) -> Provider:
        return "copilot"

    def is_available(self) -> bool:
        if not self.base_path.exists():
            return False
        # Check if any workspace has chatSessions
        for ws in self.base_path.iterdir():
            if ws.is_dir() and (ws / "chatSessions").is_dir():
                return True
        return False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_sessions(self, filters: SessionFilter | None = None) -> list[RawSession]:
        sessions: list[RawSession] = []
        if not self.base_path.exists():
            return sessions

        for ws_dir in self.base_path.iterdir():
            if not ws_dir.is_dir():
                continue
            chat_dir = ws_dir / "chatSessions"
            if not chat_dir.is_dir():
                continue

            workspace_info = self._read_workspace_json(ws_dir)

            for jsonl_file in sorted(chat_dir.glob("*.jsonl")):
                meta = self._peek_session_meta(jsonl_file)
                session_id = meta.get("sessionId", jsonl_file.stem)
                title = meta.get("customTitle")
                created = meta.get("creationDate")
                ts = _parse_epoch_ms(created) if created else None

                sessions.append(
                    RawSession(
                        id=f"copilot:{session_id}",
                        provider="copilot",
                        started_at=ts,
                        repo_path=workspace_info.get("folder"),
                        title_hint=title,
                        source_path=str(jsonl_file),
                    )
                )

        return self._apply_filters(sessions, filters)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_session(self, session_id: str) -> RawSessionData:
        native_id = session_id.removeprefix("copilot:")
        jsonl_file = self._find_session_file(native_id)
        if jsonl_file is None:
            raise FileNotFoundError(f"Session file not found for {session_id}")

        state = self._replay_session(jsonl_file)
        raw_lines = state.get("_raw_lines", [])

        messages: list[RawMessage] = []
        commands: list[RawCommand] = []
        tool_results: list[RawToolResult] = []
        files_touched: list[str] = []

        for req in state.get("requests", []):
            ts = _parse_epoch_ms(req.get("timestamp"))

            # User message
            user_msg = req.get("message", {})
            user_text = user_msg.get("text", "") if isinstance(user_msg, dict) else str(user_msg)
            if user_text:
                messages.append(RawMessage(role="user", text=user_text, timestamp=ts))

            # Response parts
            for resp_part in req.get("response", []):
                if isinstance(resp_part, str):
                    messages.append(
                        RawMessage(role="assistant", text=resp_part, timestamp=ts)
                    )
                elif isinstance(resp_part, dict):
                    # Tool invocations
                    if "toolId" in resp_part or "toolCallId" in resp_part:
                        tool_name = resp_part.get("toolId", resp_part.get("toolCallId", ""))
                        result_text = resp_part.get("result", "")
                        tool_results.append(
                            RawToolResult(
                                tool_name=tool_name,
                                result=str(result_text) if result_text else "",
                                timestamp=ts,
                                metadata=resp_part,
                            )
                        )
                        # Extract file refs and commands from tool results
                        _extract_copilot_artifacts(
                            resp_part, files_touched, commands, ts
                        )
                    elif "value" in resp_part:
                        text = resp_part.get("value", "")
                        if text:
                            messages.append(
                                RawMessage(role="assistant", text=text, timestamp=ts)
                            )

        title = state.get("customTitle")
        created = state.get("creationDate")
        started_at = _parse_epoch_ms(created) if created else None

        ws_dir = jsonl_file.parent.parent
        workspace_info = self._read_workspace_json(ws_dir)

        session = RawSession(
            id=session_id,
            provider="copilot",
            started_at=started_at,
            repo_path=workspace_info.get("folder"),
            title_hint=title,
            files_touched=files_touched,
            source_path=str(jsonl_file),
        )
        return RawSessionData(
            session=session,
            messages=messages,
            commands=commands,
            tool_results=tool_results,
            metadata=state,
            raw_lines=raw_lines,
        )

    # ------------------------------------------------------------------
    # JSONL replay
    # ------------------------------------------------------------------

    @staticmethod
    def _replay_session(path: Path) -> dict:
        """Replay kind-based incremental JSONL into a state dict."""
        state: dict = {"requests": [], "_raw_lines": []}

        for raw_line in path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            state["_raw_lines"].append(entry)
            kind = entry.get("kind")

            if kind == 0:
                # Session metadata
                for k, v in entry.items():
                    if k != "kind":
                        state[k] = v

            elif kind == 1:
                # Key-value update: {"kind": 1, "key": ["path","to","key"], "value": ...}
                key_path = entry.get("key", [])
                value = entry.get("value")
                if key_path:
                    _set_nested(state, key_path, value)

            elif kind == 2:
                # Request/response data
                key_path = entry.get("key", [])
                value = entry.get("value")
                if key_path:
                    _set_nested(state, key_path, value)

        return state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _peek_session_meta(path: Path, max_lines: int = 50) -> dict:
        """Read only the first few lines to extract session metadata fast.

        Extracts sessionId, customTitle, creationDate from kind-0 and kind-1
        entries without replaying the entire (potentially huge) file.
        """
        meta: dict = {}
        try:
            with path.open(encoding="utf-8") as f:
                for i, raw_line in enumerate(f):
                    if i >= max_lines:
                        break
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        entry = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    kind = entry.get("kind")
                    if kind == 0:
                        # Session metadata — copy all fields
                        for k, v in entry.items():
                            if k != "kind":
                                meta[k] = v
                    elif kind == 1:
                        # Key-value patches (e.g. customTitle)
                        key_path = entry.get("key", [])
                        value = entry.get("value")
                        if len(key_path) == 1:
                            meta[key_path[0]] = value
                    else:
                        # kind 2 = request data; stop scanning
                        break
        except OSError:
            pass
        return meta

    def _find_session_file(self, native_id: str) -> Path | None:
        if not self.base_path.exists():
            return None
        for ws_dir in self.base_path.iterdir():
            if not ws_dir.is_dir():
                continue
            chat_dir = ws_dir / "chatSessions"
            if not chat_dir.is_dir():
                continue
            # Try direct filename match
            candidate = chat_dir / f"{native_id}.jsonl"
            if candidate.exists():
                return candidate
            # Try scanning for matching sessionId (fast peek)
            for f in chat_dir.glob("*.jsonl"):
                meta = self._peek_session_meta(f)
                if meta.get("sessionId") == native_id:
                    return f
        return None

    @staticmethod
    def _read_workspace_json(ws_dir: Path) -> dict:
        ws_json = ws_dir / "workspace.json"
        if ws_json.exists():
            try:
                return json.loads(ws_json.read_text(encoding="utf-8"))
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


def _set_nested(d: dict, key_path: list, value: object) -> None:
    """Set a value in a nested dict/list structure following the key path."""
    current: object = d
    for i, key in enumerate(key_path[:-1]):
        if isinstance(key, int):
            if isinstance(current, list):
                while len(current) <= key:
                    current.append({})
                current = current[key]
            else:
                break
        elif isinstance(current, dict):
            if key not in current:
                # Peek at next key to decide list vs dict
                next_key = key_path[i + 1]
                current[key] = [] if isinstance(next_key, int) else {}
            current = current[key]
        else:
            break

    last_key = key_path[-1]
    if isinstance(last_key, int) and isinstance(current, list):
        while len(current) <= last_key:
            current.append(None)
        current[last_key] = value
    elif isinstance(current, dict):
        current[last_key] = value


def _parse_epoch_ms(value: int | float | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OSError, ValueError):
        return None


def _extract_copilot_artifacts(
    resp_part: dict,
    files_touched: list[str],
    commands: list[RawCommand],
    ts: datetime | None,
) -> None:
    """Extract file paths and commands from Copilot tool results."""
    tool_id = resp_part.get("toolId", "")
    result = resp_part.get("result", "")

    # File-related tools
    if any(kw in tool_id.lower() for kw in ("file", "read", "write", "edit", "create")):
        if isinstance(result, str):
            for token in result.split():
                if ("/" in token or "\\" in token) and token not in files_touched:
                    files_touched.append(token.strip("'\""))

    # Terminal/command tools
    if any(kw in tool_id.lower() for kw in ("terminal", "command", "run")):
        cmd_text = ""
        if isinstance(result, dict):
            cmd_text = result.get("command", "")
        elif isinstance(result, str):
            cmd_text = result[:200]
        if cmd_text:
            commands.append(RawCommand(command=cmd_text, timestamp=ts))
