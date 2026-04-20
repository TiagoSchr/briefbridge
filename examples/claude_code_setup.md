# BriefBridge MCP configuration for Claude Code
#
# Option A: Add to ~/.claude.json (or via Claude Code settings UI)
#
# {
#   "mcpServers": {
#     "briefbridge": {
#       "command": "bb-mcp",
#       "args": [],
#       "env": {}
#     }
#   }
# }
#
# Option B: Use the .claude/settings.json in your project root:
#
# {
#   "mcpServers": {
#     "briefbridge": {
#       "command": "bb-mcp",
#       "args": [],
#       "env": {}
#     }
#   }
# }
#
# After configuring, the following MCP tools will be available:
#   bb_sessions_list
#   bb_session_inspect
#   bb_session_pack
#   bb_session_use
#   bb_session_search
#
# You can also install slash commands by running:
#   bb wrapper install --client claude
#
# This creates ~/.claude/commands/bb_*.md files for:
#   /bb:sessions
#   /bb:inspect
#   /bb:pack
#   /bb:use
#   /bb:search
