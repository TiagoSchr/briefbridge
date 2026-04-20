"""Tests for heuristic extraction."""

from briefbridge.adapters.base import RawMessage, RawSession, RawSessionData
from briefbridge.extract.heuristic import (
    extract_decisions,
    extract_main_hypothesis,
    extract_objective,
    extract_pending_items,
)


def _make_raw(
    messages: list[RawMessage] | None = None,
    title: str | None = None,
    branch: str | None = None,
) -> RawSessionData:
    session = RawSession(
        id="test:001",
        provider="codex",
        title_hint=title,
        branch=branch,
    )
    return RawSessionData(
        session=session,
        messages=messages or [],
    )


class TestExtractObjective:
    def test_from_title(self):
        raw = _make_raw(title="Fix authentication bug in login")
        obj, conf = extract_objective(raw)
        assert obj == "Fix authentication bug in login"
        assert conf == "high"

    def test_from_first_message(self):
        raw = _make_raw(
            messages=[
                RawMessage(role="user", text="Implement the user registration endpoint"),
            ]
        )
        obj, conf = extract_objective(raw)
        assert obj is not None
        assert "registration" in obj.lower() or "implement" in obj.lower()

    def test_no_signal(self):
        raw = _make_raw()
        obj, conf = extract_objective(raw)
        assert obj is None
        assert conf == "low"


class TestExtractHypothesis:
    def test_from_diagnostic_phrase(self):
        raw = _make_raw(
            messages=[
                RawMessage(
                    role="assistant",
                    text="I think the issue is that the token validation uses local time instead of UTC.",
                ),
            ]
        )
        hyp, conf = extract_main_hypothesis(raw)
        assert hyp is not None
        assert "token" in hyp.lower() or "time" in hyp.lower() or "utc" in hyp.lower()

    def test_no_hypothesis(self):
        raw = _make_raw(
            messages=[
                RawMessage(role="user", text="Hello"),
                RawMessage(role="assistant", text="Hi! How can I help?"),
            ]
        )
        hyp, conf = extract_main_hypothesis(raw)
        assert hyp is None
        assert conf == "low"


class TestExtractDecisions:
    def test_explicit_decisions(self):
        raw = _make_raw(
            messages=[
                RawMessage(
                    role="assistant",
                    text="I decided to use Redis for caching instead of Memcached.\nAlso chose to use connection pooling.",
                ),
            ]
        )
        decisions = extract_decisions(raw)
        assert len(decisions) >= 1
        assert any("redis" in d.text.lower() for d in decisions)

    def test_no_decisions(self):
        raw = _make_raw(
            messages=[
                RawMessage(role="user", text="What is 2+2?"),
            ]
        )
        decisions = extract_decisions(raw)
        assert len(decisions) == 0


class TestExtractPendingItems:
    def test_from_todo(self):
        raw = _make_raw(
            messages=[
                RawMessage(
                    role="assistant",
                    text="TODO: audit all datetime usage across the codebase.\nStill need to add integration tests.",
                ),
            ]
        )
        items = extract_pending_items(raw)
        assert len(items) >= 1

    def test_no_pending(self):
        raw = _make_raw(
            messages=[
                RawMessage(role="assistant", text="Everything is done."),
            ]
        )
        items = extract_pending_items(raw)
        assert len(items) == 0
