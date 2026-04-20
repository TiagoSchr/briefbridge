"""Tests for the Copilot/VS Code wrapper (MCP config generation).

The Copilot integration doesn't write files — it produces config fragments
that the user pastes into VS Code settings.json.
"""

from __future__ import annotations

import json

from briefbridge.wrappers import copilot as copilot_wrapper


class TestGetMcpConfig:
    def test_returns_dict_with_briefbridge_key(self):
        cfg = copilot_wrapper.get_mcp_config()
        assert "briefbridge" in cfg

    def test_uses_stdio_transport(self):
        cfg = copilot_wrapper.get_mcp_config()
        assert cfg["briefbridge"]["type"] == "stdio"

    def test_command_is_bb_mcp(self):
        cfg = copilot_wrapper.get_mcp_config()
        assert cfg["briefbridge"]["command"] == "bb-mcp"

    def test_args_is_list(self):
        cfg = copilot_wrapper.get_mcp_config()
        assert isinstance(cfg["briefbridge"]["args"], list)


class TestGetVscodeSettingsFragment:
    def test_has_copilot_mcp_key(self):
        fragment = copilot_wrapper.get_vscode_settings_fragment()
        assert "github.copilot.chat.experimental.mcp" in fragment

    def test_servers_contains_briefbridge(self):
        fragment = copilot_wrapper.get_vscode_settings_fragment()
        servers = fragment["github.copilot.chat.experimental.mcp"]["servers"]
        assert "briefbridge" in servers

    def test_json_serializable(self):
        fragment = copilot_wrapper.get_vscode_settings_fragment()
        dumped = json.dumps(fragment)
        loaded = json.loads(dumped)
        assert loaded == fragment


class TestGetExtensionConfigSchema:
    def test_has_title(self):
        schema = copilot_wrapper.get_extension_config_schema()
        assert schema["title"] == "BriefBridge"

    def test_has_bb_path_property(self):
        schema = copilot_wrapper.get_extension_config_schema()
        assert "briefbridge.bbPath" in schema["properties"]

    def test_bb_path_default_is_bb(self):
        schema = copilot_wrapper.get_extension_config_schema()
        assert schema["properties"]["briefbridge.bbPath"]["default"] == "bb"

    def test_has_default_provider_property(self):
        schema = copilot_wrapper.get_extension_config_schema()
        assert "briefbridge.defaultProvider" in schema["properties"]

    def test_provider_enum_contains_all_providers(self):
        schema = copilot_wrapper.get_extension_config_schema()
        providers = schema["properties"]["briefbridge.defaultProvider"]["enum"]
        for expected in ("any", "copilot", "claude", "codex"):
            assert expected in providers
