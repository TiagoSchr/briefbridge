"""Tests for renderers."""

from datetime import datetime

from briefbridge.models.enums import ImportMode
from briefbridge.models.handoff import (
    ConfidenceReport,
    DecisionItem,
    HandoffPack,
    PendingItem,
    RelevantFile,
    SessionCommand,
    SessionError,
)
from briefbridge.render.json_export import render_json
from briefbridge.render.markdown import render_markdown
from briefbridge.render.plain_text import render_multi_mode, render_plain


def _sample_pack() -> HandoffPack:
    return HandoffPack(
        handoff_id="test-render-001",
        source_provider="codex",
        source_session_id="codex:abc123",
        created_at=datetime(2026, 4, 18, 14, 0, 0),
        title="Fix auth bug",
        objective="Fix token validation timezone issue",
        main_hypothesis="datetime.now() vs UTC mismatch",
        repo_name="my-app",
        branch="fix/auth-tz",
        relevant_files=[
            RelevantFile(path="src/auth/middleware.py", role="edited", changed=True, referenced_count=5),
            RelevantFile(path="src/auth/token.py", role="read", changed=False, referenced_count=3),
        ],
        errors_found=[
            SessionError(summary="AssertionError: expected 200 got 401", raw_excerpt="FAILED test_auth"),
        ],
        important_commands=[
            SessionCommand(command="pytest tests/test_auth.py", exit_code=1, summary="Tests failed"),
        ],
        decisions_made=[
            DecisionItem(text="Use UTC everywhere", confidence="high"),
        ],
        pending_items=[
            PendingItem(text="Audit all datetime usage", priority="medium"),
        ],
        confidence=ConfidenceReport(
            objective="high", main_hypothesis="medium", decisions_made="high", pending_items="medium"
        ),
    )


class TestJsonExport:
    def test_renders_valid_json(self):
        result = render_json(_sample_pack())
        import json
        data = json.loads(result)
        assert data["handoff_id"] == "test-render-001"
        assert data["source_provider"] == "codex"

    def test_roundtrip(self):
        pack = _sample_pack()
        json_str = render_json(pack)
        restored = HandoffPack.model_validate_json(json_str)
        assert restored.handoff_id == pack.handoff_id


class TestMarkdown:
    def test_has_all_sections(self):
        md = render_markdown(_sample_pack())
        assert "# BriefBridge Handoff" in md
        assert "## Objective" in md
        assert "## Main hypothesis" in md
        assert "## Relevant files" in md
        assert "## Errors found" in md
        assert "## Important commands" in md
        assert "## Decisions made" in md
        assert "## Pending items" in md
        assert "## Confidence" in md

    def test_contains_data(self):
        md = render_markdown(_sample_pack())
        assert "Fix token validation" in md
        assert "src/auth/middleware.py" in md
        assert "datetime.now()" in md


class TestPlainText:
    def test_summary_mode(self):
        result = render_plain(_sample_pack(), ImportMode.SUMMARY)
        assert "BriefBridge" in result
        assert "codex" in result

    def test_goal_mode(self):
        result = render_plain(_sample_pack(), ImportMode.GOAL)
        assert "Fix token validation" in result

    def test_hypothesis_mode(self):
        result = render_plain(_sample_pack(), ImportMode.HYPOTHESIS)
        assert "datetime.now()" in result

    def test_files_mode(self):
        result = render_plain(_sample_pack(), ImportMode.FILES)
        assert "middleware.py" in result

    def test_errors_mode(self):
        result = render_plain(_sample_pack(), ImportMode.ERRORS)
        assert "401" in result

    def test_commands_mode(self):
        result = render_plain(_sample_pack(), ImportMode.COMMANDS)
        assert "pytest" in result

    def test_decisions_mode(self):
        result = render_plain(_sample_pack(), ImportMode.DECISIONS)
        assert "UTC" in result

    def test_todos_mode(self):
        result = render_plain(_sample_pack(), ImportMode.TODOS)
        assert "datetime" in result.lower() or "audit" in result.lower()

    def test_compact_mode(self):
        result = render_plain(_sample_pack(), ImportMode.COMPACT)
        assert "Objective" in result
        assert "middleware.py" in result

    def test_full_mode(self):
        result = render_plain(_sample_pack(), ImportMode.FULL)
        assert "BriefBridge" in result
        assert "middleware.py" in result
        assert "UTC" in result

    def test_multi_mode(self):
        result = render_multi_mode(_sample_pack(), [ImportMode.GOAL, ImportMode.FILES])
        assert "Fix token validation" in result
        assert "middleware.py" in result
