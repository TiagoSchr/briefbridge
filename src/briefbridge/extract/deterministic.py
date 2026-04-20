"""Deterministic extraction — files, errors, commands, timestamps, repo info."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from briefbridge.adapters.base import RawSessionData
from briefbridge.models.handoff import RelevantFile, SessionCommand, SessionError

# Patterns that indicate an error in output
_ERROR_PATTERNS = re.compile(
    r"(Traceback \(most recent call last\)|"
    r"Error:|ERROR:|FAILED|FAIL:|"
    r"Exception:|raise |"
    r"panic:|PANIC:|"
    r"error\[E\d+\]|"
    r"SyntaxError:|TypeError:|ValueError:|KeyError:|"
    r"AttributeError:|ImportError:|ModuleNotFoundError:|"
    r"FileNotFoundError:|PermissionError:|"
    r"npm ERR!|ENOENT|EACCES)",
    re.IGNORECASE,
)

# Patterns for file paths in text
_FILE_PATH_RE = re.compile(
    r"""(?:^|[\s"'(])"""
    r"((?:[A-Za-z]:)?(?:[/\\][\w\-. ]+)+\.[\w]+)"
    r"""(?:[\s"'):]|$)"""
)

# Commands that are diagnostic or state-changing
_DIAGNOSTIC_CMDS = {"git", "npm", "pip", "pytest", "python", "node", "cargo", "make", "docker"}


def extract_relevant_files(raw: RawSessionData) -> list[RelevantFile]:
    """Rank files by edit frequency, read frequency, stack trace presence, and mentions."""
    file_scores: Counter[str] = Counter()
    file_changed: set[str] = set()
    file_roles: dict[str, str] = {}

    # Files from session metadata
    for f in raw.session.files_touched:
        file_scores[f] += 3
        file_changed.add(f)
        file_roles.setdefault(f, "edited")

    # Files mentioned in commands
    for cmd in raw.commands:
        for path in _extract_paths(cmd.command):
            file_scores[path] += 1
        # Files in stderr (stack traces)
        for path in _extract_paths(cmd.stderr):
            file_scores[path] += 2
            file_roles.setdefault(path, "stack-trace")
        for path in _extract_paths(cmd.stdout):
            file_scores[path] += 1

    # Files mentioned in messages
    for msg in raw.messages:
        for path in _extract_paths(msg.text):
            file_scores[path] += 1
            file_roles.setdefault(path, "referenced")

    # Files from tool results
    for tr in raw.tool_results:
        tool_lower = tr.tool_name.lower()
        for path in _extract_paths(tr.result):
            if any(kw in tool_lower for kw in ("write", "edit", "create", "save")):
                file_scores[path] += 3
                file_changed.add(path)
                file_roles.setdefault(path, "edited")
            elif any(kw in tool_lower for kw in ("read", "view", "cat")):
                file_scores[path] += 2
                file_roles.setdefault(path, "read")
            else:
                file_scores[path] += 1

    result: list[RelevantFile] = []
    for path, count in file_scores.most_common():
        result.append(
            RelevantFile(
                path=path,
                role=file_roles.get(path, "referenced"),
                changed=path in file_changed,
                referenced_count=count,
            )
        )
    return result


def extract_errors(raw: RawSessionData) -> list[SessionError]:
    """Extract errors from stderr, tracebacks, exit codes != 0, and error keywords."""
    errors: list[SessionError] = []
    seen_summaries: set[str] = set()

    # From commands with non-zero exit codes or error output
    for cmd in raw.commands:
        if cmd.exit_code and cmd.exit_code != 0:
            excerpt = cmd.stderr or cmd.stdout
            summary = _summarize_error(excerpt) or f"Command failed: {cmd.command[:100]}"
            if summary not in seen_summaries:
                seen_summaries.add(summary)
                errors.append(
                    SessionError(
                        summary=summary,
                        raw_excerpt=excerpt[:500],
                        source=f"command: {cmd.command[:80]}",
                        timestamp=cmd.timestamp,
                    )
                )
        elif cmd.stderr and _ERROR_PATTERNS.search(cmd.stderr):
            summary = _summarize_error(cmd.stderr)
            if summary and summary not in seen_summaries:
                seen_summaries.add(summary)
                errors.append(
                    SessionError(
                        summary=summary,
                        raw_excerpt=cmd.stderr[:500],
                        source=f"command: {cmd.command[:80]}",
                        timestamp=cmd.timestamp,
                    )
                )

    # From messages containing error patterns
    for msg in raw.messages:
        if msg.role != "user" and _ERROR_PATTERNS.search(msg.text):
            summary = _summarize_error(msg.text)
            if summary and summary not in seen_summaries:
                seen_summaries.add(summary)
                errors.append(
                    SessionError(
                        summary=summary,
                        raw_excerpt=msg.text[:500],
                        source=f"message ({msg.role})",
                        timestamp=msg.timestamp,
                    )
                )

    return errors


def extract_commands(raw: RawSessionData) -> list[SessionCommand]:
    """Keep commands that failed, validated solution, changed state, or helped diagnose."""
    result: list[SessionCommand] = []
    seen: set[str] = set()

    for cmd in raw.commands:
        if cmd.command in seen:
            continue

        keep = False
        summary = ""

        # Failed commands are always interesting
        if cmd.exit_code is not None and cmd.exit_code != 0:
            keep = True
            summary = f"Failed (exit {cmd.exit_code})"

        # Diagnostic commands
        first_token = cmd.command.split()[0] if cmd.command.split() else ""
        base_cmd = first_token.split("/")[-1].split("\\")[-1]
        if base_cmd in _DIAGNOSTIC_CMDS:
            keep = True
            summary = summary or "Diagnostic/build command"

        # Test commands
        if any(kw in cmd.command.lower() for kw in ("test", "spec", "check", "lint")):
            keep = True
            summary = summary or "Test/validation"

        # State-changing commands
        if any(kw in cmd.command.lower() for kw in ("install", "migrate", "init", "build", "deploy")):
            keep = True
            summary = summary or "State-changing command"

        if keep:
            seen.add(cmd.command)
            result.append(
                SessionCommand(
                    command=cmd.command,
                    exit_code=cmd.exit_code,
                    summary=summary,
                    timestamp=cmd.timestamp,
                )
            )

    return result


def extract_timestamps(raw: RawSessionData) -> tuple[datetime | None, datetime | None]:
    """Extract session start and end timestamps."""
    started = raw.session.started_at
    ended = raw.session.ended_at

    # Fallback: scan messages
    if not started or not ended:
        all_ts = [
            m.timestamp
            for m in raw.messages
            if m.timestamp
        ]
        all_ts.extend(c.timestamp for c in raw.commands if c.timestamp)
        if all_ts:
            started = started or min(all_ts)
            ended = ended or max(all_ts)

    return started, ended


def extract_repo_info(
    raw: RawSessionData,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Extract repo_path, repo_name, branch, commit_head from session data."""
    repo_path = raw.session.repo_path
    branch = raw.session.branch
    commit_head: str | None = None

    # Try to infer repo name from path
    repo_name: str | None = None
    if repo_path:
        # Normalize separators and take last meaningful segment
        normalized = repo_path.replace("\\", "/").rstrip("/")
        repo_name = normalized.split("/")[-1] if "/" in normalized else normalized

    # Look in metadata
    if not branch:
        branch = raw.metadata.get("branch") or raw.metadata.get("gitBranch")
    if not commit_head:
        commit_head = raw.metadata.get("commit_head") or raw.metadata.get("commitHead")

    # Scan messages for branch/commit refs
    if not branch:
        for msg in raw.messages[:5]:
            m = re.search(r"(?:branch|on)\s+['\"]?(\S+)['\"]?", msg.text, re.IGNORECASE)
            if m:
                branch = m.group(1)
                break

    return repo_path, repo_name, branch, commit_head


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_paths(text: str) -> list[str]:
    """Extract file-like paths from text."""
    if not text:
        return []
    matches = _FILE_PATH_RE.findall(text)
    # Also get simple relative paths
    result: list[str] = []
    for m in matches:
        cleaned = m.strip().strip("'\"(),:")
        if cleaned and len(cleaned) > 3:
            result.append(cleaned)
    return result


def _summarize_error(text: str) -> str:
    """Create a one-line summary of an error from its raw text."""
    if not text:
        return ""
    lines = text.strip().splitlines()

    # Look for the actual error line in a traceback
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        if any(
            line.startswith(prefix)
            for prefix in (
                "Error:", "TypeError:", "ValueError:", "KeyError:",
                "AttributeError:", "ImportError:", "ModuleNotFoundError:",
                "FileNotFoundError:", "SyntaxError:", "PermissionError:",
                "RuntimeError:", "OSError:", "npm ERR!",
            )
        ):
            return line[:200]
        if re.match(r"^\w+Error:", line):
            return line[:200]

    # Fallback: first non-empty line
    for line in lines:
        line = line.strip()
        if line:
            return line[:200]
    return ""
