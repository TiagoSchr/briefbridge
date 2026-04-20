"""Tests for the Claude Code adapter."""

from pathlib import Path

from briefbridge.adapters.claude import ClaudeAdapter, _decode_project_dir


class TestDecodeProjectDir:
    def test_windows_path(self):
        assert _decode_project_dir("c--Users--User--projects--api-gateway") == "C:\\Users\\User\\projects\\api-gateway"

    def test_unix_path(self):
        assert _decode_project_dir("-home--user--project") == "/home/user/project"


class TestClaudeAdapter:
    def test_is_available(self, claude_fixtures: Path):
        adapter = ClaudeAdapter(claude_fixtures)
        assert adapter.is_available() is True

    def test_is_not_available(self, tmp_path: Path):
        adapter = ClaudeAdapter(tmp_path / "nonexistent")
        assert adapter.is_available() is False

    def test_discover_sessions(self, claude_fixtures: Path):
        adapter = ClaudeAdapter(claude_fixtures)
        sessions = adapter.discover_sessions()
        assert len(sessions) >= 1
        s = sessions[0]
        assert s.provider == "claude"
        assert "sess-claude-001" in s.id

    def test_read_session(self, claude_fixtures: Path):
        adapter = ClaudeAdapter(claude_fixtures)
        data = adapter.read_session("claude:sess-claude-001")

        assert data.session.provider == "claude"
        assert data.session.branch == "fix/rate-limiter"
        assert len(data.messages) > 0

        # Should have title from ai-title entry
        assert data.session.title_hint == "Debug API rate limiter returning 429 too aggressively"

        # Should have user message about rate limiter
        user_msgs = [m for m in data.messages if m.role == "user"]
        assert len(user_msgs) >= 1
        assert "rate limiter" in user_msgs[0].text.lower()

    def test_read_nonexistent(self, claude_fixtures: Path):
        adapter = ClaudeAdapter(claude_fixtures)
        try:
            adapter.read_session("claude:nonexistent")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass
