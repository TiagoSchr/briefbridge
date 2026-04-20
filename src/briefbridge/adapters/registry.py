"""Adapter registry — factory and auto-detection of available providers."""

from __future__ import annotations

from briefbridge.adapters.base import BaseAdapter
from briefbridge.adapters.claude import ClaudeAdapter
from briefbridge.adapters.codex import CodexAdapter
from briefbridge.adapters.copilot import CopilotAdapter
from briefbridge.config import BriefBridgeConfig
from briefbridge.models.enums import Provider


def _build_adapters(config: BriefBridgeConfig) -> dict[Provider, BaseAdapter]:
    return {
        "codex": CodexAdapter(config.codex_path),
        "claude": ClaudeAdapter(config.claude_path),
        "copilot": CopilotAdapter(config.copilot_path),
    }


def get_adapter(provider: Provider, config: BriefBridgeConfig | None = None) -> BaseAdapter:
    cfg = config or BriefBridgeConfig.load()
    adapters = _build_adapters(cfg)
    if provider not in adapters:
        raise ValueError(f"Unknown provider: {provider}")
    return adapters[provider]


def get_all_adapters(config: BriefBridgeConfig | None = None) -> list[BaseAdapter]:
    cfg = config or BriefBridgeConfig.load()
    return list(_build_adapters(cfg).values())


def get_available_adapters(config: BriefBridgeConfig | None = None) -> list[BaseAdapter]:
    return [a for a in get_all_adapters(config) if a.is_available()]
