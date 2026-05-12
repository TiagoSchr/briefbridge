"""Tests for the Claude Code wrapper (slash command integration).

Validates that install/uninstall create and remove the correct files under
~/.claude/commands/bb/ using a tmp_path so the real filesystem is never touched.
The expected slash commands are /bb:sessions, /bb:inspect, /bb:pack, /bb:use,
/bb:search, /bb:context.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from briefbridge.wrappers import claude as claude_wrapper

_EXPECTED_COMMANDS = ["bb:sessions", "bb:inspect", "bb:pack", "bb:use", "bb:search", "bb:context"]
_EXPECTED_FILES = ["sessions.md", "inspect.md", "pack.md", "use.md", "search.md", "context.md"]


class TestListCommands:
    def test_returns_all_commands(self):
        cmds = claude_wrapper.list_commands()
        for cmd in _EXPECTED_COMMANDS:
            assert cmd in cmds

    def test_all_have_bb_prefix(self):
        for cmd in claude_wrapper.list_commands():
            assert cmd.startswith("bb:")


class TestInstall:
    def test_creates_command_files(self, tmp_path: Path):
        installed = claude_wrapper.install(commands_dir=tmp_path, verbose=False)
        for fname in _EXPECTED_FILES:
            assert (tmp_path / fname).exists(), f"Missing {fname}"

    def test_returns_list_of_paths(self, tmp_path: Path):
        result = claude_wrapper.install(commands_dir=tmp_path, verbose=False)
        assert isinstance(result, list)
        assert len(result) == len(_EXPECTED_COMMANDS)
        for p in result:
            assert isinstance(p, Path)

    def test_command_files_have_yaml_frontmatter(self, tmp_path: Path):
        claude_wrapper.install(commands_dir=tmp_path, verbose=False)
        for fname in _EXPECTED_FILES:
            content = (tmp_path / fname).read_text(encoding="utf-8")
            assert content.startswith("---"), f"{fname} missing YAML frontmatter"
            assert "description:" in content

    def test_sessions_file_mentions_bb_sessions(self, tmp_path: Path):
        claude_wrapper.install(commands_dir=tmp_path, verbose=False)
        content = (tmp_path / "sessions.md").read_text(encoding="utf-8")
        assert "bb sessions" in content

    def test_inspect_file_mentions_bb_inspect(self, tmp_path: Path):
        claude_wrapper.install(commands_dir=tmp_path, verbose=False)
        content = (tmp_path / "inspect.md").read_text(encoding="utf-8")
        assert "bb inspect" in content

    def test_pack_file_mentions_bb_pack(self, tmp_path: Path):
        claude_wrapper.install(commands_dir=tmp_path, verbose=False)
        content = (tmp_path / "pack.md").read_text(encoding="utf-8")
        assert "bb pack" in content

    def test_use_file_mentions_bb_use(self, tmp_path: Path):
        claude_wrapper.install(commands_dir=tmp_path, verbose=False)
        content = (tmp_path / "use.md").read_text(encoding="utf-8")
        assert "bb use" in content

    def test_idempotent(self, tmp_path: Path):
        """Calling install twice should not raise."""
        claude_wrapper.install(commands_dir=tmp_path, verbose=False)
        claude_wrapper.install(commands_dir=tmp_path, verbose=False)
        assert (tmp_path / "sessions.md").exists()

    def test_cleans_up_old_flat_files(self, tmp_path: Path):
        """Old bb_sessions.md flat files (pre-refactor) are removed on install."""
        old_file = tmp_path.parent / "bb_sessions.md"
        old_file.write_text("old content")
        claude_wrapper.install(commands_dir=tmp_path, verbose=False)
        assert not old_file.exists()


class TestUninstall:
    def test_removes_command_dir(self, tmp_path: Path):
        claude_wrapper.install(commands_dir=tmp_path, verbose=False)
        claude_wrapper.uninstall(commands_dir=tmp_path, verbose=False)
        assert not tmp_path.exists()

    def test_noop_when_not_installed(self, tmp_path: Path):
        """Uninstalling when command dir doesn't exist should not raise."""
        not_there = tmp_path / "bb"
        claude_wrapper.uninstall(commands_dir=not_there, verbose=False)
