"""Tests for the CLI commands using typer's CliRunner."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from briefbridge.cli import app

runner = CliRunner()


class TestCliHelp:
    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "briefbridge" in result.output.lower() or "handoff" in result.output.lower()

    def test_sessions_help(self):
        result = runner.invoke(app, ["sessions", "--help"])
        assert result.exit_code == 0
        assert "--last" in result.output

    def test_inspect_help(self):
        result = runner.invoke(app, ["inspect", "--help"])
        assert result.exit_code == 0

    def test_pack_help(self):
        result = runner.invoke(app, ["pack", "--help"])
        assert result.exit_code == 0

    def test_use_help(self):
        result = runner.invoke(app, ["use", "--help"])
        assert result.exit_code == 0
        assert "--mode" in result.output

    def test_export_help(self):
        result = runner.invoke(app, ["export", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output

    def test_ask_help(self):
        result = runner.invoke(app, ["ask", "--help"])
        assert result.exit_code == 0
