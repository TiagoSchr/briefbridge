"""Heuristic extraction — objective, hypothesis, decisions, pending items.

All extraction is keyword-based and deterministic (no LLM). Each function
returns a confidence level alongside the extracted value. When there is
insufficient signal the value is ``None`` with confidence ``"low"``.
"""

from __future__ import annotations

import re
from typing import Literal

from briefbridge.adapters.base import RawSessionData
from briefbridge.models.handoff import DecisionItem, PendingItem

ConfLevel = Literal["high", "medium", "low"]

# ------------------------------------------------------------------
# Objective
# ------------------------------------------------------------------

_OBJECTIVE_KEYWORDS = re.compile(
    r"(fix|implement|add|create|build|refactor|debug|investigate|resolve|update|"
    r"migrate|remove|optimize|write|set\s?up|configure|deploy|integrate)",
    re.IGNORECASE,
)


def extract_objective(raw: RawSessionData) -> tuple[str | None, ConfLevel]:
    """Infer session objective from first user message, title, and branch name."""
    candidates: list[tuple[str, ConfLevel]] = []

    # Title is the best signal
    title = raw.session.title_hint
    if title and len(title) > 5:
        candidates.append((title, "high"))

    # First user message
    for msg in raw.messages:
        if msg.role == "user" and msg.text.strip():
            first_line = msg.text.strip().splitlines()[0][:300]
            if _OBJECTIVE_KEYWORDS.search(first_line):
                candidates.append((first_line, "high"))
            else:
                candidates.append((first_line, "medium"))
            break

    # Branch name can hint at objective
    branch = raw.session.branch
    if branch and branch not in ("main", "master", "develop", "dev"):
        readable = branch.replace("-", " ").replace("_", " ").replace("/", ": ")
        candidates.append((f"Branch: {readable}", "low"))

    if not candidates:
        return None, "low"

    # Pick the highest-confidence candidate
    for conf in ("high", "medium", "low"):
        for text, c in candidates:
            if c == conf:
                return text, c

    return candidates[0][0], candidates[0][1]


# ------------------------------------------------------------------
# Main hypothesis
# ------------------------------------------------------------------

_HYPOTHESIS_PATTERNS = re.compile(
    r"(I think|maybe|could be|might be|probably|looks like|"
    r"let'?s try|my guess|hypothesis|suspect|"
    r"the issue (?:is|seems|appears)|root cause|"
    r"the problem (?:is|seems|appears))",
    re.IGNORECASE,
)


def extract_main_hypothesis(raw: RawSessionData) -> tuple[str | None, ConfLevel]:
    """Infer main hypothesis from exploratory/diagnostic phrases."""
    best: str | None = None
    best_conf: ConfLevel = "low"

    for msg in raw.messages:
        if msg.role not in ("assistant", "developer"):
            continue
        for line in msg.text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = _HYPOTHESIS_PATTERNS.search(line)
            if m:
                # Take the full sentence
                sentence = _extract_sentence(line, m.start())
                if sentence and len(sentence) > 10:
                    best = sentence
                    best_conf = "medium"
                    # If multiple signals exist, bump to high
                    if _HYPOTHESIS_PATTERNS.findall(msg.text).__len__() > 2:
                        best_conf = "high"
                    break
        if best_conf == "high":
            break

    return best, best_conf


# ------------------------------------------------------------------
# Decisions
# ------------------------------------------------------------------

_DECISION_PATTERNS = re.compile(
    r"(decided to|going with|chose|switched to|"
    r"will use|opted for|settled on|"
    r"let'?s go with|picking|choosing|"
    r"the approach is|we('ll| will) use)",
    re.IGNORECASE,
)


def extract_decisions(raw: RawSessionData) -> list[DecisionItem]:
    """Extract decisions from decision-indicating phrases in messages."""
    decisions: list[DecisionItem] = []
    seen: set[str] = set()

    for msg in raw.messages:
        for line in msg.text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = _DECISION_PATTERNS.search(line)
            if m:
                sentence = _extract_sentence(line, m.start())
                if sentence and sentence not in seen and len(sentence) > 10:
                    seen.add(sentence)
                    # Confidence based on explicitness
                    conf: ConfLevel = "medium"
                    if any(
                        kw in sentence.lower()
                        for kw in ("decided to", "chose", "settled on")
                    ):
                        conf = "high"
                    decisions.append(DecisionItem(text=sentence, confidence=conf))

    return decisions


# ------------------------------------------------------------------
# Pending items
# ------------------------------------------------------------------

_PENDING_PATTERNS = re.compile(
    r"(TODO|FIXME|HACK|XXX|still need to|haven'?t tested|"
    r"remaining|not yet|left to do|needs? (?:to be |)(?:fixed|tested|implemented|done)|"
    r"should (?:also |still )|"
    r"don'?t forget|"
    r"open question|unclear|not sure about|"
    r"next step)",
    re.IGNORECASE,
)


def extract_pending_items(raw: RawSessionData) -> list[PendingItem]:
    """Extract pending work from TODO markers, unresolved questions, etc."""
    items: list[PendingItem] = []
    seen: set[str] = set()

    for msg in raw.messages:
        for line in msg.text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = _PENDING_PATTERNS.search(line)
            if m:
                sentence = _extract_sentence(line, m.start())
                if sentence and sentence not in seen and len(sentence) > 5:
                    seen.add(sentence)
                    # Priority heuristic
                    priority: Literal["high", "medium", "low"] = "medium"
                    low = sentence.lower()
                    if any(kw in low for kw in ("TODO", "FIXME", "still need to", "needs to be fixed")):
                        priority = "high"
                    elif any(kw in low for kw in ("open question", "unclear", "not sure")):
                        priority = "low"
                    items.append(PendingItem(text=sentence, priority=priority))

    return items


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_sentence(text: str, start: int) -> str:
    """Extract a single sentence from text around the match position."""
    # Walk backwards to sentence start
    i = start
    while i > 0 and text[i - 1] not in ".!?\n":
        i -= 1

    # Walk forward to sentence end
    j = start
    while j < len(text) and text[j] not in ".!?\n":
        j += 1
    if j < len(text) and text[j] in ".!?":
        j += 1

    return text[i:j].strip()
