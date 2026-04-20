"""Tests for SQLite storage backend."""

from datetime import datetime

from briefbridge.models.handoff import (
    ConfidenceReport,
    HandoffPack,
    RelevantFile,
    SessionError,
)
from briefbridge.storage.sqlite import StorageBackend


class TestStorageBackend:
    def _make_storage(self) -> StorageBackend:
        return StorageBackend(":memory:")

    def test_upsert_and_list_sessions(self):
        db = self._make_storage()
        db.upsert_session(
            id="codex:abc",
            provider="codex",
            started_at=datetime(2026, 4, 18, 14, 0),
            repo_path="/home/user/my-app",
            repo_name="my-app",
            branch="main",
            title="Fix bug",
        )
        results = db.list_sessions()
        assert len(results) == 1
        assert results[0].id == "codex:abc"
        assert results[0].title == "Fix bug"
        db.close()

    def test_filter_by_provider(self):
        db = self._make_storage()
        db.upsert_session(id="codex:1", provider="codex", title="A")
        db.upsert_session(id="claude:1", provider="claude", title="B")
        results = db.list_sessions(provider="codex")
        assert len(results) == 1
        assert results[0].provider == "codex"
        db.close()

    def test_upsert_and_get_handoff(self):
        db = self._make_storage()
        pack = HandoffPack(
            handoff_id="h-001",
            source_provider="codex",
            source_session_id="codex:abc",
            title="Test pack",
            objective="Test objective",
            relevant_files=[RelevantFile(path="src/main.py", role="edited", changed=True)],
            errors_found=[SessionError(summary="TypeError")],
        )
        db.upsert_handoff(pack)
        restored = db.get_handoff("codex:abc")
        assert restored is not None
        assert restored.handoff_id == "h-001"
        assert restored.title == "Test pack"
        assert len(restored.relevant_files) == 1
        db.close()

    def test_search_fts(self):
        db = self._make_storage()
        pack = HandoffPack(
            handoff_id="h-002",
            source_provider="claude",
            source_session_id="claude:xyz",
            title="Rate limiter fix",
            objective="Fix rate limiting for API gateway",
        )
        db.upsert_handoff(pack)
        results = db.search("rate limiter")
        assert len(results) >= 1
        assert "rate" in results[0].title.lower()
        db.close()

    def test_get_nonexistent_handoff(self):
        db = self._make_storage()
        result = db.get_handoff("nonexistent")
        assert result is None
        db.close()
