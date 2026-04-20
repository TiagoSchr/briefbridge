"""Tests for deterministic extraction."""

from datetime import datetime, timezone

from briefbridge.adapters.base import RawCommand, RawMessage, RawSession, RawSessionData
from briefbridge.extract.deterministic import (
    extract_commands,
    extract_errors,
    extract_relevant_files,
    extract_repo_info,
    extract_timestamps,
)


def _make_raw(
    messages: list[RawMessage] | None = None,
    commands: list[RawCommand] | None = None,
    files_touched: list[str] | None = None,
    repo_path: str | None = None,
    branch: str | None = None,
) -> RawSessionData:
    session = RawSession(
        id="test:001",
        provider="codex",
        repo_path=repo_path,
        branch=branch,
        files_touched=files_touched or [],
    )
    return RawSessionData(
        session=session,
        messages=messages or [],
        commands=commands or [],
    )


class TestExtractRelevantFiles:
    def test_from_files_touched(self):
        raw = _make_raw(files_touched=["src/main.py", "src/utils.py"])
        files = extract_relevant_files(raw)
        assert len(files) >= 2
        paths = [f.path for f in files]
        assert "src/main.py" in paths

    def test_from_commands(self):
        raw = _make_raw(
            commands=[
                RawCommand(command="cat /app/src/config.py", stdout="content", exit_code=0),
            ]
        )
        files = extract_relevant_files(raw)
        paths = [f.path for f in files]
        assert "/app/src/config.py" in paths

    def test_from_stderr_stack_trace(self):
        raw = _make_raw(
            commands=[
                RawCommand(
                    command="python app.py",
                    stderr='File "/app/src/handler.py", line 42, in process\n  raise ValueError',
                    exit_code=1,
                ),
            ]
        )
        files = extract_relevant_files(raw)
        paths = [f.path for f in files]
        assert any("handler.py" in p for p in paths)


class TestExtractErrors:
    def test_from_failed_command(self):
        raw = _make_raw(
            commands=[
                RawCommand(
                    command="pytest tests/",
                    stderr="FAILED tests/test_auth.py::test_login",
                    exit_code=1,
                ),
            ]
        )
        errors = extract_errors(raw)
        assert len(errors) >= 1
        assert "FAILED" in errors[0].summary or "failed" in errors[0].summary.lower()

    def test_from_traceback_in_message(self):
        raw = _make_raw(
            messages=[
                RawMessage(
                    role="assistant",
                    text="Traceback (most recent call last):\n  File 'x.py'\nTypeError: expected str got int",
                ),
            ]
        )
        errors = extract_errors(raw)
        assert len(errors) >= 1

    def test_no_errors(self):
        raw = _make_raw(
            commands=[
                RawCommand(command="ls", exit_code=0),
            ]
        )
        errors = extract_errors(raw)
        assert len(errors) == 0


class TestExtractCommands:
    def test_keeps_failed(self):
        raw = _make_raw(
            commands=[
                RawCommand(command="pytest tests/", exit_code=1),
                RawCommand(command="ls", exit_code=0),
            ]
        )
        cmds = extract_commands(raw)
        assert any(c.command == "pytest tests/" for c in cmds)

    def test_keeps_diagnostic(self):
        raw = _make_raw(
            commands=[
                RawCommand(command="git status", exit_code=0),
                RawCommand(command="echo hello", exit_code=0),
            ]
        )
        cmds = extract_commands(raw)
        assert any(c.command == "git status" for c in cmds)


class TestExtractTimestamps:
    def test_from_session(self):
        raw = _make_raw()
        ts_start = datetime(2026, 4, 18, 14, 0, tzinfo=timezone.utc)
        raw.session.started_at = ts_start
        start, end = extract_timestamps(raw)
        assert start == ts_start

    def test_from_messages_fallback(self):
        ts1 = datetime(2026, 4, 18, 14, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 4, 18, 15, 0, tzinfo=timezone.utc)
        raw = _make_raw(
            messages=[
                RawMessage(role="user", text="hi", timestamp=ts1),
                RawMessage(role="assistant", text="hello", timestamp=ts2),
            ]
        )
        start, end = extract_timestamps(raw)
        assert start == ts1
        assert end == ts2


class TestExtractRepoInfo:
    def test_from_session(self):
        raw = _make_raw(repo_path="/home/user/projects/my-app", branch="main")
        path, name, branch, commit = extract_repo_info(raw)
        assert path == "/home/user/projects/my-app"
        assert name == "my-app"
        assert branch == "main"
