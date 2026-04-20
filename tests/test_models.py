"""Tests for Pydantic models."""

from datetime import datetime

from briefbridge.models.handoff import (
    ConfidenceReport,
    DecisionItem,
    HandoffPack,
    PendingItem,
    RawSourcePointer,
    RelevantFile,
    SessionCommand,
    SessionError,
)


class TestRelevantFile:
    def test_basic(self):
        f = RelevantFile(path="src/main.py", role="edited", changed=True, referenced_count=5)
        assert f.path == "src/main.py"
        assert f.changed is True
        assert f.referenced_count == 5

    def test_defaults(self):
        f = RelevantFile(path="test.py")
        assert f.role == ""
        assert f.changed is False
        assert f.referenced_count is None


class TestSessionError:
    def test_with_timestamp(self):
        ts = datetime(2026, 4, 18, 14, 0, 0)
        e = SessionError(summary="TypeError: x is not a function", raw_excerpt="line 42", source="stderr", timestamp=ts)
        assert e.summary == "TypeError: x is not a function"
        assert e.timestamp == ts

    def test_minimal(self):
        e = SessionError(summary="Something failed")
        assert e.raw_excerpt == ""
        assert e.source == ""
        assert e.timestamp is None


class TestSessionCommand:
    def test_full(self):
        c = SessionCommand(command="pytest tests/", exit_code=1, summary="Tests failed")
        assert c.exit_code == 1

    def test_no_exit_code(self):
        c = SessionCommand(command="ls")
        assert c.exit_code is None


class TestDecisionItem:
    def test_confidence(self):
        d = DecisionItem(text="Use Redis for caching", confidence="high")
        assert d.confidence == "high"

    def test_default_confidence(self):
        d = DecisionItem(text="Something")
        assert d.confidence == "medium"


class TestPendingItem:
    def test_priority(self):
        p = PendingItem(text="Add integration tests", priority="high")
        assert p.priority == "high"


class TestConfidenceReport:
    def test_defaults(self):
        c = ConfidenceReport()
        assert c.objective == "low"
        assert c.main_hypothesis == "low"


class TestRawSourcePointer:
    def test_basic(self):
        r = RawSourcePointer(provider="codex", local_path="/path/to/session.jsonl", kind="session_jsonl")
        assert r.provider == "codex"


class TestHandoffPack:
    def test_full_pack(self):
        pack = HandoffPack(
            handoff_id="test-001",
            source_provider="codex",
            source_session_id="codex:abc123",
            title="Fix auth bug",
            objective="Fix token validation timezone issue",
            main_hypothesis="datetime.now() vs UTC mismatch",
            relevant_files=[
                RelevantFile(path="src/auth/middleware.py", role="edited", changed=True),
            ],
            errors_found=[
                SessionError(summary="AssertionError: expected 200 got 401"),
            ],
            important_commands=[
                SessionCommand(command="pytest tests/test_auth.py", exit_code=1, summary="Failed"),
            ],
            decisions_made=[
                DecisionItem(text="Use UTC everywhere", confidence="high"),
            ],
            pending_items=[
                PendingItem(text="Audit all datetime usage", priority="medium"),
            ],
            confidence=ConfidenceReport(
                objective="high",
                main_hypothesis="medium",
                decisions_made="high",
                pending_items="medium",
            ),
        )
        assert pack.handoff_id == "test-001"
        assert len(pack.relevant_files) == 1
        assert len(pack.errors_found) == 1

    def test_minimal_pack(self):
        pack = HandoffPack(
            handoff_id="test-002",
            source_provider="unknown",
            source_session_id="unknown:xyz",
        )
        assert pack.relevant_files == []
        assert pack.objective is None
        assert pack.confidence.objective == "low"

    def test_serialization_roundtrip(self):
        pack = HandoffPack(
            handoff_id="test-003",
            source_provider="claude",
            source_session_id="claude:sess-001",
            title="Test roundtrip",
            objective="Verify serialization",
        )
        json_str = pack.model_dump_json()
        restored = HandoffPack.model_validate_json(json_str)
        assert restored.handoff_id == pack.handoff_id
        assert restored.title == pack.title
        assert restored.objective == pack.objective
