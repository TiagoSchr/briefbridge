"""Ingest manager — orchestrates adapter → extraction → HandoffPack assembly."""

from __future__ import annotations

import uuid
from datetime import datetime

from briefbridge.adapters.base import BaseAdapter, RawSessionData
from briefbridge.adapters.registry import get_adapter, get_available_adapters
from briefbridge.config import BriefBridgeConfig
from briefbridge.extract.deterministic import (
    extract_commands,
    extract_errors,
    extract_relevant_files,
    extract_repo_info,
    extract_timestamps,
)
from briefbridge.extract.heuristic import (
    extract_decisions,
    extract_main_hypothesis,
    extract_objective,
    extract_pending_items,
)
from briefbridge.models.enums import Provider
from briefbridge.models.handoff import ConfidenceReport, HandoffPack, RawSourcePointer


class IngestManager:
    def __init__(self, config: BriefBridgeConfig | None = None) -> None:
        self.config = config or BriefBridgeConfig.load()

    def resolve_adapter(self, session_id: str) -> BaseAdapter:
        """Determine which adapter to use from a prefixed session id."""
        provider: Provider | None = None
        for prefix in ("codex:", "claude:", "copilot:"):
            if session_id.startswith(prefix):
                provider = prefix.rstrip(":")  # type: ignore[assignment]
                break
        if provider:
            return get_adapter(provider, self.config)

        # If no prefix, scan all adapters
        for adapter in get_available_adapters(self.config):
            try:
                adapter.read_session(session_id)
                return adapter
            except FileNotFoundError:
                continue
        raise FileNotFoundError(f"No adapter found for session: {session_id}")

    def read(self, session_id: str) -> RawSessionData:
        adapter = self.resolve_adapter(session_id)
        return adapter.read_session(session_id)

    def build_handoff(self, session_id: str) -> HandoffPack:
        """Run the full pipeline: ingest → extract → assemble HandoffPack."""
        raw = self.read(session_id)

        # Deterministic extraction
        relevant_files = extract_relevant_files(raw)
        errors_found = extract_errors(raw)
        important_commands = extract_commands(raw)
        started_at, ended_at = extract_timestamps(raw)
        repo_path, repo_name, branch, commit_head = extract_repo_info(raw)

        # Heuristic extraction
        objective, obj_conf = extract_objective(raw)
        hypothesis, hyp_conf = extract_main_hypothesis(raw)
        decisions = extract_decisions(raw)
        pending = extract_pending_items(raw)

        # Confidence report
        confidence = ConfidenceReport(
            objective=obj_conf,
            main_hypothesis=hyp_conf,
            decisions_made="high" if len(decisions) > 2 else ("medium" if decisions else "low"),
            pending_items="high" if len(pending) > 2 else ("medium" if pending else "low"),
        )

        return HandoffPack(
            handoff_id=str(uuid.uuid4()),
            source_provider=raw.session.provider,
            source_session_id=session_id,
            created_at=datetime.now(),
            session_started_at=started_at,
            session_ended_at=ended_at,
            repo_path=repo_path,
            repo_name=repo_name,
            branch=branch,
            commit_head=commit_head,
            title=raw.session.title_hint or objective,
            objective=objective,
            main_hypothesis=hypothesis,
            relevant_files=relevant_files,
            errors_found=errors_found,
            important_commands=important_commands,
            decisions_made=decisions,
            pending_items=pending,
            confidence=confidence,
            raw_sources=[
                RawSourcePointer(
                    provider=raw.session.provider,
                    local_path=raw.session.source_path,
                    kind="session_jsonl",
                )
            ],
        )
