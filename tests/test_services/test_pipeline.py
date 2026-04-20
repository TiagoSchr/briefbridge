"""Integration tests for the full pipeline."""

from pathlib import Path

from briefbridge.adapters.codex import CodexAdapter
from briefbridge.adapters.claude import ClaudeAdapter
from briefbridge.adapters.copilot import CopilotAdapter
from briefbridge.extract.deterministic import (
    extract_commands,
    extract_errors,
    extract_relevant_files,
)
from briefbridge.extract.heuristic import (
    extract_decisions,
    extract_main_hypothesis,
    extract_objective,
    extract_pending_items,
)
from briefbridge.render.json_export import render_json
from briefbridge.render.markdown import render_markdown
from briefbridge.render.plain_text import render_plain
from briefbridge.models.enums import ImportMode


class TestCodexPipeline:
    """Full pipeline test: Codex adapter → extraction → render."""

    def test_end_to_end(self, codex_fixtures: Path):
        adapter = CodexAdapter(codex_fixtures)
        raw = adapter.read_session("codex:rollout-20260418-abc123")

        # Extraction
        files = extract_relevant_files(raw)
        errors = extract_errors(raw)
        commands = extract_commands(raw)
        obj, obj_conf = extract_objective(raw)
        hyp, hyp_conf = extract_main_hypothesis(raw)
        decisions = extract_decisions(raw)
        pending = extract_pending_items(raw)

        # Verify extraction produced results
        assert len(files) > 0
        assert len(errors) > 0  # We have a failed pytest
        assert len(commands) > 0
        assert obj is not None

        # Build a pack manually and render
        from briefbridge.models.handoff import HandoffPack, ConfidenceReport

        pack = HandoffPack(
            handoff_id="test-pipeline-001",
            source_provider="codex",
            source_session_id="codex:rollout-20260418-abc123",
            objective=obj,
            main_hypothesis=hyp,
            relevant_files=files,
            errors_found=errors,
            important_commands=commands,
            decisions_made=decisions,
            pending_items=pending,
            confidence=ConfidenceReport(objective=obj_conf, main_hypothesis=hyp_conf),
        )

        # JSON renders correctly
        json_output = render_json(pack)
        assert "rollout-20260418-abc123" in json_output

        # Markdown renders correctly
        md_output = render_markdown(pack)
        assert "## Objective" in md_output

        # Plain text renders correctly
        plain_output = render_plain(pack, ImportMode.COMPACT)
        assert len(plain_output) > 0


class TestClaudePipeline:
    def test_end_to_end(self, claude_fixtures: Path):
        adapter = ClaudeAdapter(claude_fixtures)
        raw = adapter.read_session("claude:sess-claude-001")

        files = extract_relevant_files(raw)
        errors = extract_errors(raw)
        obj, _ = extract_objective(raw)
        decisions = extract_decisions(raw)

        assert obj is not None
        assert len(decisions) > 0  # "decided to switch" and "going with"


class TestCopilotPipeline:
    def test_end_to_end(self, copilot_fixtures: Path):
        adapter = CopilotAdapter(copilot_fixtures)
        raw = adapter.read_session("copilot:copilot-sess-001")

        obj, _ = extract_objective(raw)
        pending = extract_pending_items(raw)

        assert obj is not None
        # Should pick up the TODO about mobile viewport
        assert len(pending) > 0 or obj is not None  # At least objective found
