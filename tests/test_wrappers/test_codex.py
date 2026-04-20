"""Tests for the Codex wrapper (Agent Skills integration).

Validates that install/uninstall create and remove the correct files under
~/.agents/skills/briefbridge/ using a tmp_path so the real filesystem is
never touched.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from briefbridge.wrappers import codex as codex_wrapper


class TestResolvebbCmd:
    def test_returns_string(self):
        result = codex_wrapper._resolve_bb_cmd()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_prefers_shutil_which(self):
        with patch("briefbridge.wrappers.codex.shutil.which", return_value="/usr/local/bin/bb"):
            result = codex_wrapper._resolve_bb_cmd()
        # Use Path for comparison so the test passes on Windows (backslashes) too
        assert Path(result) == Path("/usr/local/bin/bb")

    def test_falls_back_to_python_module(self):
        with patch("briefbridge.wrappers.codex.shutil.which", return_value=None):
            result = codex_wrapper._resolve_bb_cmd()
        assert "-m briefbridge" in result


class TestBuildSkillMd:
    def test_contains_bb_cmd(self):
        md = codex_wrapper._build_skill_md("/usr/bin/bb")
        assert "/usr/bin/bb" in md

    def test_contains_never_read_files_instruction(self):
        md = codex_wrapper._build_skill_md("/usr/bin/bb")
        assert "do not read" in md.lower() or "never read" in md.lower()

    def test_contains_all_main_commands(self):
        md = codex_wrapper._build_skill_md("/usr/bin/bb")
        for cmd in ("sessions", "inspect", "pack", "use"):
            assert cmd in md

    def test_has_yaml_frontmatter(self):
        md = codex_wrapper._build_skill_md("/usr/bin/bb")
        assert md.startswith("---")
        assert "name: briefbridge" in md


class TestInstall:
    def test_creates_skill_md(self, tmp_path: Path):
        installed = codex_wrapper.install(skills_dir=tmp_path, verbose=False)
        skill_md = tmp_path / "briefbridge" / "SKILL.md"
        assert skill_md in installed
        assert skill_md.exists()

    def test_creates_openai_yaml(self, tmp_path: Path):
        installed = codex_wrapper.install(skills_dir=tmp_path, verbose=False)
        openai_yaml = tmp_path / "briefbridge" / "agents" / "openai.yaml"
        assert openai_yaml in installed
        assert openai_yaml.exists()

    def test_skill_md_content_has_bb_path(self, tmp_path: Path):
        with patch("briefbridge.wrappers.codex._resolve_bb_cmd", return_value="/fake/bb"):
            codex_wrapper.install(skills_dir=tmp_path, verbose=False)
        content = (tmp_path / "briefbridge" / "SKILL.md").read_text(encoding="utf-8")
        assert "/fake/bb" in content

    def test_openai_yaml_has_display_name(self, tmp_path: Path):
        codex_wrapper.install(skills_dir=tmp_path, verbose=False)
        content = (tmp_path / "briefbridge" / "agents" / "openai.yaml").read_text()
        assert "BriefBridge" in content

    def test_idempotent(self, tmp_path: Path):
        """Calling install twice should not raise and should overwrite cleanly."""
        codex_wrapper.install(skills_dir=tmp_path, verbose=False)
        codex_wrapper.install(skills_dir=tmp_path, verbose=False)
        assert (tmp_path / "briefbridge" / "SKILL.md").exists()

    def test_returns_list_of_paths(self, tmp_path: Path):
        result = codex_wrapper.install(skills_dir=tmp_path, verbose=False)
        assert isinstance(result, list)
        assert len(result) == 2
        for p in result:
            assert isinstance(p, Path)


class TestUninstall:
    def test_removes_skill_dir(self, tmp_path: Path):
        codex_wrapper.install(skills_dir=tmp_path, verbose=False)
        codex_wrapper.uninstall(skills_dir=tmp_path, verbose=False)
        assert not (tmp_path / "briefbridge").exists()

    def test_noop_when_not_installed(self, tmp_path: Path):
        """Uninstalling when skill dir doesn't exist should not raise."""
        codex_wrapper.uninstall(skills_dir=tmp_path, verbose=False)


class TestListCommands:
    def test_returns_list(self):
        cmds = codex_wrapper.list_commands()
        assert isinstance(cmds, list)
        assert "briefbridge" in cmds
