"""Session listing and inspection service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from briefbridge.adapters.base import RawSession, SessionFilter
from briefbridge.adapters.registry import get_available_adapters
from briefbridge.config import BriefBridgeConfig, detect_repo_root
from briefbridge.models.enums import Provider
from briefbridge.storage.sqlite import SessionSummary, StorageBackend


@dataclass
class SessionDetail:
    """Detailed session view for the inspect command."""

    id: str
    provider: str
    started_at: datetime | None
    ended_at: datetime | None
    repo_path: str | None
    repo_name: str | None
    branch: str | None
    title: str | None
    files_touched: list[str]
    message_count: int
    command_count: int
    error_hints: list[str]
    first_user_message: str | None


class SessionsService:
    def __init__(
        self,
        config: BriefBridgeConfig | None = None,
        storage: StorageBackend | None = None,
    ) -> None:
        self.config = config or BriefBridgeConfig.load()
        self.storage = storage

    def list_sessions(
        self,
        *,
        last_hours: float | None = None,
        repo: str | None = None,
        branch: str | None = None,
        provider: Provider | None = None,
    ) -> list[SessionSummary]:
        """List sessions from all available adapters, caching to storage."""
        # If "auto", resolve repo from cwd
        if repo == "auto":
            repo = detect_repo_root()

        filters = SessionFilter(
            last_hours=last_hours,
            repo=repo,
            branch=branch,
            provider=provider,
        )

        adapters = get_available_adapters(self.config)
        if provider:
            adapters = [a for a in adapters if a.provider_name == provider]

        all_sessions: list[RawSession] = []
        for adapter in adapters:
            try:
                sessions = adapter.discover_sessions(filters)
                all_sessions.extend(sessions)
            except Exception:
                continue

        # Cache to storage if available
        if self.storage:
            for s in all_sessions:
                self.storage.upsert_session(
                    id=s.id,
                    provider=s.provider,
                    started_at=s.started_at,
                    ended_at=s.ended_at,
                    repo_path=s.repo_path,
                    branch=s.branch,
                    title=s.title_hint,
                    source_path=s.source_path,
                    files_touched=s.files_touched,
                )

        # Sort by start time descending
        all_sessions.sort(
            key=lambda s: s.started_at.timestamp() if s.started_at else 0,
            reverse=True,
        )

        return [
            SessionSummary(
                id=s.id,
                provider=s.provider,
                started_at=s.started_at.isoformat() if s.started_at else None,
                ended_at=s.ended_at.isoformat() if s.ended_at else None,
                repo_path=s.repo_path,
                repo_name=_repo_name(s.repo_path),
                branch=s.branch,
                title=s.title_hint,
                files_touched=s.files_touched,
            )
            for s in all_sessions
        ]

    def inspect_session(self, session_id: str) -> SessionDetail:
        """Show detailed session information."""
        from briefbridge.ingest.manager import IngestManager

        mgr = IngestManager(self.config)
        raw = mgr.read(session_id)

        error_hints: list[str] = []
        for cmd in raw.commands:
            if cmd.exit_code and cmd.exit_code != 0:
                snippet = (cmd.stderr or cmd.stdout)[:100]
                error_hints.append(f"$ {cmd.command[:60]} → exit {cmd.exit_code}: {snippet}")

        first_user = None
        for msg in raw.messages:
            if msg.role == "user" and msg.text.strip():
                first_user = msg.text.strip()[:300]
                break

        return SessionDetail(
            id=raw.session.id,
            provider=raw.session.provider,
            started_at=raw.session.started_at,
            ended_at=raw.session.ended_at,
            repo_path=raw.session.repo_path,
            repo_name=_repo_name(raw.session.repo_path),
            branch=raw.session.branch,
            title=raw.session.title_hint,
            files_touched=raw.session.files_touched,
            message_count=len(raw.messages),
            command_count=len(raw.commands),
            error_hints=error_hints,
            first_user_message=first_user,
        )


def _repo_name(repo_path: str | None) -> str | None:
    if not repo_path:
        return None
    normalized = repo_path.replace("\\", "/").rstrip("/")
    return normalized.split("/")[-1] if "/" in normalized else normalized
