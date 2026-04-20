"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def codex_fixtures() -> Path:
    return FIXTURES_DIR / "codex"


@pytest.fixture
def claude_fixtures() -> Path:
    return FIXTURES_DIR / "claude"


@pytest.fixture
def copilot_fixtures() -> Path:
    return FIXTURES_DIR / "copilot"
