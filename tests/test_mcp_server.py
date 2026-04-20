"""Tests for the MCP server tools — bb_sessions_list, bb_session_inspect, etc."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from briefbridge.config import BriefBridgeConfig
from briefbridge.models.handoff import (
    ConfidenceReport,
    DecisionItem,
    HandoffPack,
    PendingItem,
    RelevantFile,
    SessionCommand,
    SessionError,
)
from briefbridge.storage.sqlite import SessionSummary, StorageBackend


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_pack(session_id: str = "claude:test-001", provider: str = "claude") -> HandoffPack:
    return HandoffPack(
        handoff_id="hpack-001",
        source_provider=provider,  # type: ignore[arg-type]
        source_session_id=session_id,
        repo_name="my-api",
        branch="feature/auth",
        objective="Fix JWT validation bug",
        main_hypothesis="Token expiry check is using wrong timezone",
        relevant_files=[
            RelevantFile(path="src/auth.py", role="edited", changed=True),
            RelevantFile(path="tests/test_auth.py", role="edited", changed=True),
        ],
        errors_found=[
            SessionError(summary="AssertionError: token expired", source="pytest"),
        ],
        important_commands=[
            SessionCommand(command="pytest tests/test_auth.py", exit_code=1, summary="Failed (exit 1)"),
            SessionCommand(command="pytest tests/test_auth.py", exit_code=0, summary="Passed"),
        ],
        decisions_made=[
            DecisionItem(text="Use UTC for all timestamp comparisons", confidence="high"),
        ],
        pending_items=[
            PendingItem(text="Add integration test for refresh tokens", priority="medium"),
        ],
        confidence=ConfidenceReport(objective="high", main_hypothesis="medium"),
    )


def _make_summary(session_id: str = "claude:test-001") -> SessionSummary:
    return SessionSummary(
        id=session_id,
        provider="claude",
        started_at="2026-04-19T10:00:00",
        ended_at="2026-04-19T12:00:00",
        repo_path="/home/user/my-api",
        repo_name="my-api",
        branch="feature/auth",
        title="Fix JWT bug",
        files_touched=["src/auth.py", "tests/test_auth.py"],
    )


# ---------------------------------------------------------------------------
# bb_sessions_list
# ---------------------------------------------------------------------------


class TestBbSessionsList:
    def test_returns_sessions_structure(self):
        """bb_sessions_list returns correct schema."""
        import briefbridge.mcp_server as srv

        mock_summary = _make_summary()
        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.SessionsService") as MockSvc:
                    MockSvc.return_value.list_sessions.return_value = [mock_summary]
                    result = srv.bb_sessions_list(hours=24, provider="any")

        assert "sessions" in result
        assert len(result["sessions"]) == 1
        s = result["sessions"][0]
        assert s["id"] == "claude:test-001"
        assert s["provider"] == "claude"
        assert s["repo"] == "my-api"
        assert s["files_count"] == 2
        assert s["title"] == "Fix JWT bug"

    def test_provider_filter_passed_through(self):
        """provider='claude' is passed through to SessionsService.list_sessions."""
        import briefbridge.mcp_server as srv

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.SessionsService") as MockSvc:
                    MockSvc.return_value.list_sessions.return_value = []
                    srv.bb_sessions_list(hours=24, provider="claude")
                    call_kwargs = MockSvc.return_value.list_sessions.call_args.kwargs
                    assert call_kwargs["provider"] == "claude"

    def test_any_provider_resolves_to_none(self):
        """provider='any' is resolved to None for no filter."""
        import briefbridge.mcp_server as srv

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.SessionsService") as MockSvc:
                    MockSvc.return_value.list_sessions.return_value = []
                    srv.bb_sessions_list(hours=24, provider="any")
                    call_kwargs = MockSvc.return_value.list_sessions.call_args.kwargs
                    assert call_kwargs["provider"] is None

    def test_empty_result(self):
        """Returns empty sessions list gracefully."""
        import briefbridge.mcp_server as srv

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.SessionsService") as MockSvc:
                    MockSvc.return_value.list_sessions.return_value = []
                    result = srv.bb_sessions_list()
        assert result == {"sessions": []}


# ---------------------------------------------------------------------------
# bb_session_inspect
# ---------------------------------------------------------------------------


class TestBbSessionInspect:
    def test_returns_inspect_structure(self):
        """bb_session_inspect returns full handoff data."""
        import briefbridge.mcp_server as srv

        pack = _make_pack()
        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.get_or_generate.return_value = pack
                    result = srv.bb_session_inspect("claude:test-001")

        assert result["id"] == "claude:test-001"
        assert result["provider"] == "claude"
        assert result["repo"] == "my-api"
        assert result["branch"] == "feature/auth"
        assert result["objective"] == "Fix JWT validation bug"
        assert len(result["relevant_files"]) == 2
        assert result["relevant_files"][0]["path"] == "src/auth.py"
        assert len(result["errors_found"]) == 1
        assert len(result["decisions_made"]) == 1
        assert len(result["pending_items"]) == 1

    def test_session_not_found(self):
        """Returns error dict when session is not found."""
        import briefbridge.mcp_server as srv

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.get_or_generate.side_effect = FileNotFoundError
                    result = srv.bb_session_inspect("claude:nonexistent")

        assert "error" in result
        assert "claude:nonexistent" in result["error"]


# ---------------------------------------------------------------------------
# bb_session_pack
# ---------------------------------------------------------------------------


class TestBbSessionPack:
    def test_returns_all_formats(self):
        """bb_session_pack returns markdown, plain_text, and json."""
        import briefbridge.mcp_server as srv

        pack = _make_pack()
        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.get_or_generate.return_value = pack
                    result = srv.bb_session_pack("claude:test-001", mode="compact")

        assert "handoff_id" in result
        assert "markdown" in result
        assert "plain_text" in result
        assert "json" in result
        assert isinstance(result["json"], dict)
        assert result["json"]["source_session_id"] == "claude:test-001"

    def test_markdown_contains_objective(self):
        """Rendered markdown includes the objective."""
        import briefbridge.mcp_server as srv

        pack = _make_pack()
        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.get_or_generate.return_value = pack
                    result = srv.bb_session_pack("claude:test-001")

        assert "Fix JWT validation bug" in result["markdown"]

    def test_session_not_found(self):
        """Returns error dict when session is not found."""
        import briefbridge.mcp_server as srv

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.get_or_generate.side_effect = FileNotFoundError
                    result = srv.bb_session_pack("claude:missing")

        assert "error" in result


# ---------------------------------------------------------------------------
# bb_session_use
# ---------------------------------------------------------------------------


class TestBbSessionUse:
    def test_returns_context_block(self):
        """bb_session_use returns a non-empty context_block."""
        import briefbridge.mcp_server as srv

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.use_pack.return_value = "## Context\nFix JWT bug"
                    result = srv.bb_session_use("claude:test-001", mode="compact")

        assert "context_block" in result
        assert "Fix JWT bug" in result["context_block"]

    def test_default_mode_is_compact(self):
        """Default mode is compact."""
        import briefbridge.mcp_server as srv
        from briefbridge.models.enums import ImportMode

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.use_pack.return_value = "block"
                    srv.bb_session_use("claude:test-001")
                    call_args = MockSvc.return_value.use_pack.call_args
                    modes = call_args[0][1]  # positional arg: modes list
                    assert ImportMode.COMPACT in modes

    def test_multi_mode_parsed(self):
        """Comma-separated modes are all parsed."""
        import briefbridge.mcp_server as srv
        from briefbridge.models.enums import ImportMode

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.use_pack.return_value = "block"
                    srv.bb_session_use("claude:test-001", mode="goal,files,errors")
                    call_args = MockSvc.return_value.use_pack.call_args
                    modes = call_args[0][1]
                    assert ImportMode.GOAL in modes
                    assert ImportMode.FILES in modes
                    assert ImportMode.ERRORS in modes

    def test_session_not_found(self):
        """Returns error dict when session is not found."""
        import briefbridge.mcp_server as srv

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.use_pack.side_effect = FileNotFoundError
                    result = srv.bb_session_use("claude:missing")

        assert "error" in result


# ---------------------------------------------------------------------------
# bb_session_search
# ---------------------------------------------------------------------------


class TestBbSessionSearch:
    def test_returns_matches_structure(self):
        """bb_session_search returns correct schema."""
        import briefbridge.mcp_server as srv
        from briefbridge.storage.sqlite import SearchResult

        mock_result = SearchResult(
            session_id="claude:test-001",
            title="Fix JWT bug",
            snippet="JWT validation error",
            rank=-1.5,
        )
        mock_storage = MagicMock()
        mock_storage.search.return_value = [mock_result]

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=mock_storage):
                with patch("briefbridge.mcp_server.SessionsService") as MockSessionsSvc:
                    MockSessionsSvc.return_value.list_sessions.return_value = []
                    with patch("briefbridge.mcp_server.SearchService"):
                        result = srv.bb_session_search("JWT validation", hours=72)

        assert "matches" in result
        assert len(result["matches"]) == 1
        assert result["matches"][0]["session_id"] == "claude:test-001"
        assert result["matches"][0]["snippet"] == "JWT validation error"

    def test_empty_matches(self):
        """Returns empty matches gracefully."""
        import briefbridge.mcp_server as srv

        mock_storage = MagicMock()
        mock_storage.search.return_value = []

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=mock_storage):
                with patch("briefbridge.mcp_server.SessionsService") as MockSvc:
                    MockSvc.return_value.list_sessions.return_value = []
                    with patch("briefbridge.mcp_server.SearchService"):
                        result = srv.bb_session_search("nonexistent query")

        assert result == {"matches": []}


# ---------------------------------------------------------------------------
# Schema contract tests — ensure output shapes match documented spec
# ---------------------------------------------------------------------------


class TestMcpSchemaContract:
    """Verify that each tool returns the documented schema keys."""

    def test_sessions_list_schema_keys(self):
        import briefbridge.mcp_server as srv

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.SessionsService") as MockSvc:
                    MockSvc.return_value.list_sessions.return_value = [_make_summary()]
                    result = srv.bb_sessions_list()

        assert "sessions" in result
        session = result["sessions"][0]
        for key in ("id", "provider", "time", "repo", "files_count", "title", "status"):
            assert key in session, f"Missing key '{key}' in session"

    def test_inspect_schema_keys(self):
        import briefbridge.mcp_server as srv

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.get_or_generate.return_value = _make_pack()
                    result = srv.bb_session_inspect("claude:test-001")

        for key in ("id", "provider", "repo", "branch", "objective", "main_hypothesis",
                    "relevant_files", "errors_found", "important_commands",
                    "decisions_made", "pending_items"):
            assert key in result, f"Missing key '{key}' in inspect result"

    def test_pack_schema_keys(self):
        import briefbridge.mcp_server as srv

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.get_or_generate.return_value = _make_pack()
                    result = srv.bb_session_pack("claude:test-001")

        for key in ("handoff_id", "markdown", "plain_text", "json"):
            assert key in result, f"Missing key '{key}' in pack result"

    def test_use_schema_keys(self):
        import briefbridge.mcp_server as srv

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=MagicMock()):
                with patch("briefbridge.mcp_server.HandoffService") as MockSvc:
                    MockSvc.return_value.use_pack.return_value = "context"
                    result = srv.bb_session_use("claude:test-001")

        assert "context_block" in result

    def test_search_schema_keys(self):
        import briefbridge.mcp_server as srv

        mock_storage = MagicMock()
        mock_storage.search.return_value = []

        with patch.object(srv, "_get_config", return_value=BriefBridgeConfig()):
            with patch.object(srv, "_get_storage", return_value=mock_storage):
                with patch("briefbridge.mcp_server.SessionsService") as MockSvc:
                    MockSvc.return_value.list_sessions.return_value = []
                    with patch("briefbridge.mcp_server.SearchService"):
                        result = srv.bb_session_search("test query")

        assert "matches" in result
