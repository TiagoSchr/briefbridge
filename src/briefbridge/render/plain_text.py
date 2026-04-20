"""Plain-text renderer with selective import modes.

Generates compact text blocks optimized for pasting into another coding agent.
"""

from __future__ import annotations

from briefbridge.models.enums import ImportMode
from briefbridge.models.handoff import HandoffPack


def render_plain(pack: HandoffPack, mode: ImportMode = ImportMode.SUMMARY) -> str:
    """Render a HandoffPack section as a paste-ready plain-text block."""
    renderers: dict[ImportMode, _Renderer] = {
        ImportMode.SUMMARY: _render_summary,
        ImportMode.GOAL: _render_goal,
        ImportMode.HYPOTHESIS: _render_hypothesis,
        ImportMode.FILES: _render_files,
        ImportMode.ERRORS: _render_errors,
        ImportMode.COMMANDS: _render_commands,
        ImportMode.DECISIONS: _render_decisions,
        ImportMode.TODOS: _render_todos,
        ImportMode.COMPACT: _render_compact,
        ImportMode.FULL: _render_full,
    }
    renderer = renderers.get(mode, _render_summary)
    return renderer(pack)


from typing import Callable

_Renderer = Callable[[HandoffPack], str]


def _render_summary(pack: HandoffPack) -> str:
    parts = [f"[BriefBridge Handoff — {pack.source_provider}]"]
    if pack.title:
        parts.append(f"Title: {pack.title}")
    if pack.objective:
        parts.append(f"Objective: {pack.objective}")
    if pack.repo_name:
        parts.append(f"Repo: {pack.repo_name}")
    if pack.branch:
        parts.append(f"Branch: {pack.branch}")
    if pack.relevant_files:
        top = pack.relevant_files[:5]
        parts.append(f"Key files: {', '.join(f.path for f in top)}")
    if pack.errors_found:
        parts.append(f"Errors: {len(pack.errors_found)} found")
    if pack.pending_items:
        parts.append(f"Pending: {len(pack.pending_items)} items")
    return "\n".join(parts)


def _render_goal(pack: HandoffPack) -> str:
    return pack.objective or "No objective identified"


def _render_hypothesis(pack: HandoffPack) -> str:
    return pack.main_hypothesis or "No hypothesis identified"


def _render_files(pack: HandoffPack) -> str:
    if not pack.relevant_files:
        return "No relevant files identified"
    lines = ["Relevant files:"]
    for f in pack.relevant_files:
        marker = " [changed]" if f.changed else ""
        lines.append(f"  - {f.path} ({f.role}){marker}")
    return "\n".join(lines)


def _render_errors(pack: HandoffPack) -> str:
    if not pack.errors_found:
        return "No errors found"
    lines = ["Errors found:"]
    for i, err in enumerate(pack.errors_found, 1):
        lines.append(f"  {i}. {err.summary}")
        if err.raw_excerpt:
            # Indent excerpt
            for excerpt_line in err.raw_excerpt.splitlines()[:3]:
                lines.append(f"     {excerpt_line}")
    return "\n".join(lines)


def _render_commands(pack: HandoffPack) -> str:
    if not pack.important_commands:
        return "No important commands"
    lines = ["Important commands:"]
    for cmd in pack.important_commands:
        exit_str = f" (exit {cmd.exit_code})" if cmd.exit_code is not None else ""
        lines.append(f"  $ {cmd.command}{exit_str}")
    return "\n".join(lines)


def _render_decisions(pack: HandoffPack) -> str:
    if not pack.decisions_made:
        return "No decisions identified"
    lines = ["Decisions:"]
    for d in pack.decisions_made:
        lines.append(f"  - [{d.confidence}] {d.text}")
    return "\n".join(lines)


def _render_todos(pack: HandoffPack) -> str:
    if not pack.pending_items:
        return "No pending items"
    lines = ["Pending items:"]
    for p in pack.pending_items:
        lines.append(f"  - [{p.priority}] {p.text}")
    return "\n".join(lines)


def _render_compact(pack: HandoffPack) -> str:
    """Compact mode: objective + hypothesis + top 5 files + top 3 errors + top 5 pending."""
    sections: list[str] = [f"[BriefBridge Handoff — {pack.source_provider}]"]

    if pack.objective:
        sections.append(f"Objective: {pack.objective}")

    if pack.main_hypothesis:
        sections.append(f"Hypothesis: {pack.main_hypothesis}")

    if pack.relevant_files:
        top = pack.relevant_files[:5]
        sections.append("Key files:")
        for f in top:
            marker = " [changed]" if f.changed else ""
            sections.append(f"  - {f.path}{marker}")

    if pack.errors_found:
        top = pack.errors_found[:3]
        sections.append("Errors:")
        for err in top:
            sections.append(f"  - {err.summary}")

    if pack.pending_items:
        top = pack.pending_items[:5]
        sections.append("Pending:")
        for p in top:
            sections.append(f"  - {p.text}")

    return "\n".join(sections)


def _render_full(pack: HandoffPack) -> str:
    """Full mode: all sections combined."""
    sections = [
        _render_summary(pack),
        "",
        _render_hypothesis(pack),
        "",
        _render_files(pack),
        "",
        _render_errors(pack),
        "",
        _render_commands(pack),
        "",
        _render_decisions(pack),
        "",
        _render_todos(pack),
    ]
    return "\n".join(sections)


def render_multi_mode(pack: HandoffPack, modes: list[ImportMode]) -> str:
    """Render multiple selective modes combined."""
    parts: list[str] = []
    for mode in modes:
        parts.append(render_plain(pack, mode))
    return "\n\n".join(parts)
