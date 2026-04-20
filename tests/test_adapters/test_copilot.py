"""Tests for the Copilot Chat adapter."""

from pathlib import Path

from briefbridge.adapters.copilot import CopilotAdapter


class TestCopilotAdapter:
    def test_is_available(self, copilot_fixtures: Path):
        adapter = CopilotAdapter(copilot_fixtures)
        assert adapter.is_available() is True

    def test_is_not_available(self, tmp_path: Path):
        adapter = CopilotAdapter(tmp_path / "nonexistent")
        assert adapter.is_available() is False

    def test_discover_sessions(self, copilot_fixtures: Path):
        adapter = CopilotAdapter(copilot_fixtures)
        sessions = adapter.discover_sessions()
        assert len(sessions) >= 1
        s = sessions[0]
        assert s.provider == "copilot"
        assert s.title_hint == "Fix CSS layout bug in dashboard"

    def test_read_session(self, copilot_fixtures: Path):
        adapter = CopilotAdapter(copilot_fixtures)
        data = adapter.read_session("copilot:copilot-sess-001")

        assert data.session.provider == "copilot"
        assert len(data.messages) > 0

        # Should have user message about CSS
        user_msgs = [m for m in data.messages if m.role == "user"]
        assert len(user_msgs) >= 1
        assert "dashboard" in user_msgs[0].text.lower() or "grid" in user_msgs[0].text.lower()

    def test_replay_incremental(self, copilot_fixtures: Path):
        adapter = CopilotAdapter(copilot_fixtures)
        jsonl = copilot_fixtures / "ws-hash-001" / "chatSessions" / "copilot-sess-001.jsonl"
        state = adapter._replay_session(jsonl)
        assert state.get("sessionId") == "copilot-sess-001"
        assert state.get("customTitle") == "Fix CSS layout bug in dashboard"
        assert len(state.get("requests", [])) == 2
