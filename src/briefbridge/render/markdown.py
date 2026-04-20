"""Markdown renderer for HandoffPack."""

from __future__ import annotations

from briefbridge.models.handoff import HandoffPack


def render_markdown(pack: HandoffPack) -> str:
    """Render a HandoffPack as structured Markdown."""
    lines: list[str] = []

    # Header
    lines.append("# BriefBridge Handoff")
    lines.append("")
    lines.append(f"**Provider:** {pack.source_provider}")
    lines.append(f"**Session:** {pack.source_session_id}")
    if pack.repo_name or pack.repo_path:
        lines.append(f"**Repo:** {pack.repo_name or pack.repo_path}")
    if pack.branch:
        lines.append(f"**Branch:** {pack.branch}")
    if pack.commit_head:
        lines.append(f"**Commit:** {pack.commit_head}")
    lines.append(f"**Created:** {pack.created_at.isoformat()}")
    if pack.session_started_at:
        lines.append(f"**Session started:** {pack.session_started_at.isoformat()}")
    if pack.session_ended_at:
        lines.append(f"**Session ended:** {pack.session_ended_at.isoformat()}")
    lines.append("")

    # Objective
    lines.append("## Objective")
    lines.append("")
    lines.append(pack.objective or "_Not identified_")
    lines.append("")

    # Main hypothesis
    lines.append("## Main hypothesis")
    lines.append("")
    lines.append(pack.main_hypothesis or "_Not identified_")
    lines.append("")

    # Relevant files
    lines.append("## Relevant files")
    lines.append("")
    if pack.relevant_files:
        lines.append("| Path | Role | Changed | Refs |")
        lines.append("|------|------|---------|------|")
        for f in pack.relevant_files:
            changed = "yes" if f.changed else "no"
            refs = str(f.referenced_count) if f.referenced_count is not None else "-"
            lines.append(f"| `{f.path}` | {f.role} | {changed} | {refs} |")
    else:
        lines.append("_No files identified_")
    lines.append("")

    # Errors found
    lines.append("## Errors found")
    lines.append("")
    if pack.errors_found:
        for i, err in enumerate(pack.errors_found, 1):
            lines.append(f"### Error {i}")
            lines.append(f"**Summary:** {err.summary}")
            if err.source:
                lines.append(f"**Source:** {err.source}")
            if err.timestamp:
                lines.append(f"**Time:** {err.timestamp.isoformat()}")
            if err.raw_excerpt:
                lines.append("")
                lines.append("```")
                lines.append(err.raw_excerpt[:500])
                lines.append("```")
            lines.append("")
    else:
        lines.append("_No errors found_")
    lines.append("")

    # Important commands
    lines.append("## Important commands")
    lines.append("")
    if pack.important_commands:
        for cmd in pack.important_commands:
            exit_str = f" (exit {cmd.exit_code})" if cmd.exit_code is not None else ""
            lines.append(f"- `{cmd.command}`{exit_str} — {cmd.summary}")
    else:
        lines.append("_No important commands_")
    lines.append("")

    # Decisions made
    lines.append("## Decisions made")
    lines.append("")
    if pack.decisions_made:
        for d in pack.decisions_made:
            lines.append(f"- [{d.confidence}] {d.text}")
    else:
        lines.append("_No decisions identified_")
    lines.append("")

    # Pending items
    lines.append("## Pending items")
    lines.append("")
    if pack.pending_items:
        for p in pack.pending_items:
            lines.append(f"- [{p.priority}] {p.text}")
    else:
        lines.append("_No pending items_")
    lines.append("")

    # Confidence
    lines.append("## Confidence")
    lines.append("")
    lines.append(f"- **Objective:** {pack.confidence.objective}")
    lines.append(f"- **Main hypothesis:** {pack.confidence.main_hypothesis}")
    lines.append(f"- **Decisions:** {pack.confidence.decisions_made}")
    lines.append(f"- **Pending items:** {pack.confidence.pending_items}")
    lines.append("")

    return "\n".join(lines)
