"""Tests for the Codex CLI adapter."""

from pathlib import Path

from briefbridge.adapters.codex import CodexAdapter


class TestCodexAdapter:
    def test_is_available(self, codex_fixtures: Path):
        adapter = CodexAdapter(codex_fixtures)
        assert adapter.is_available() is True

    def test_is_not_available(self, tmp_path: Path):
        adapter = CodexAdapter(tmp_path / "nonexistent")
        assert adapter.is_available() is False

    def test_discover_sessions(self, codex_fixtures: Path):
        adapter = CodexAdapter(codex_fixtures)
        sessions = adapter.discover_sessions()
        assert len(sessions) == 3
        assert sessions[0].id == "codex:rollout-20260418-abc123"
        assert sessions[0].provider == "codex"
        assert sessions[0].title_hint == "Fix auth token validation bug"

    def test_read_session(self, codex_fixtures: Path):
        adapter = CodexAdapter(codex_fixtures)
        data = adapter.read_session("codex:rollout-20260418-abc123")

        assert data.session.provider == "codex"
        assert data.session.repo_path == "/home/user/projects/my-app"
        assert len(data.messages) > 0
        assert len(data.commands) > 0

        # Should have user message about auth bug
        user_msgs = [m for m in data.messages if m.role == "user"]
        assert len(user_msgs) >= 1
        assert "authentication" in user_msgs[0].text.lower()

        # Should have the failed test command
        failed = [c for c in data.commands if c.exit_code and c.exit_code != 0]
        assert len(failed) >= 1

    def test_read_nonexistent(self, codex_fixtures: Path):
        adapter = CodexAdapter(codex_fixtures)
        try:
            adapter.read_session("codex:nonexistent")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass
