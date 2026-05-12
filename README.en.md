<div align="center">

# 🌉 BriefBridge

**Cross-agent session handoff — continue your work in any AI coding tool without losing context.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-142%20passing-brightgreen)](https://github.com/TiagoSchr/briefbridge)

*Leia em [Português](README.md)*

</div>

---

BriefBridge reads local session data from **GitHub Copilot Chat**, **Claude Code**, and **Codex**, extracts structured context — objectives, files touched, errors, decisions, pending items — and makes it available as a paste-ready handoff block you can drop into any other tool.

**All clients share the same MCP backend. Only the interface changes.**

---

## Why does this exist?

When you switch AI coding tools mid-task, you lose all context. You have to re-explain the objective, re-list changed files, and re-describe every error you hit. BriefBridge automates that transfer.

- 🔍 **Reads** local session files from each tool (no API calls, no data leaving your machine)
- 🧠 **Extracts** objective, hypothesis, files, errors, commands, decisions, and pending items
- 📦 **Packs** everything into a structured handoff block in seconds
- 🔌 **Works** as a CLI, VS Code extension, or MCP server — pick what fits your workflow

```
$ bb use codex:019cdf99 --mode compact

[BriefBridge Handoff — codex]
Objective: Add manual user registration to admin panel
Key files:
  - src/admin/users.py
  - src/auth/signup.py
Errors: IntegrityError: UNIQUE constraint failed: users.email
Pending: Test flow with duplicate user
```

> Paste that block at the top of your next message and you are back in context immediately.

---

## Table of Contents

- [How it works](#how-it-works)
- [Installation](#installation)
- [GitHub Copilot / VS Code](#github-copilot--vs-code)
- [Claude Code](#claude-code)
- [Codex](#codex)
- [CLI Reference](#cli-reference)
- [MCP Tools Reference](#mcp-tools-reference)
- [Development](#development)

---

## How it works

```
+---------------------------------------------------+
|                  bb-mcp (STDIO)                   |
|  bb_sessions_list    bb_session_inspect           |
|  bb_session_pack     bb_session_use               |
|  bb_session_search                                |
+---------------------+-----------------------------+
                      |
          +-----------v-----------+
          |    briefbridge core   |
          |  adapters / extract   |
          |  storage / render     |
          +-----------+-----------+
             ^        ^        ^
        ~/.claude/ ~/.codex/ %APPDATA%\Code\User\workspaceStorage\
```

Each tool saves its sessions locally on disk. BriefBridge knows where each one stores those files and reads them directly — no API, no token, no internet connection needed.

| Tool | Where data lives |
|---|---|
| **Claude Code** | `~/.claude/projects/*/` |
| **Codex** | `~/.codex/sessions/YYYY/MM/DD/` |
| **GitHub Copilot** | `%APPDATA%\Code\User\workspaceStorage\` (Windows) |

```
src/briefbridge/
├── cli.py                # Typer CLI — bb, briefbridge, bb-mcp
├── mcp_server.py         # FastMCP server — 5 tools via STDIO
├── config.py             # Platform-aware path detection
├── adapters/             # One adapter per provider
│   ├── claude.py         # Reads ~/.claude/
│   ├── codex.py          # Reads ~/.codex/
│   └── copilot.py        # Reads VS Code workspaceStorage
├── extract/
│   ├── deterministic.py  # Files, errors, commands, repo
│   └── heuristic.py      # Objective, hypothesis, decisions, TODOs
├── ingest/               # Orchestrate adapter -> extract -> pack
├── models/               # Pydantic v2 models (HandoffPack, RawSession...)
├── render/               # JSON, Markdown, plain-text output
├── services/             # Sessions, handoff, search business logic
├── storage/              # SQLite FTS5 cache
└── wrappers/             # Per-client install helpers
    ├── claude.py         # /bb:* slash commands
    ├── codex.py          # $briefbridge skill
    └── copilot.py        # MCP config helper
```

---

## Installation

**Requirements:** Python 3.12+

```bash
git clone https://github.com/TiagoSchr/briefbridge.git
cd briefbridge
pip install -e .
```

Verify:

```bash
bb --help
bb sessions
```

---

## GitHub Copilot / VS Code

BriefBridge ships a VS Code extension with the `@bb` chat participant.

### Option A — VS Code Extension (recommended)

Build and install the extension from source:

```bash
cd vscode-ext
npm install
npm run package          # produces briefbridge.vsix
code --install-extension briefbridge.vsix
```

Restart VS Code, then use it in the Copilot Chat panel:

```
@bb /sessions
@bb /sessions claude          # filter by provider
@bb /inspect <session_id>
@bb /use     <session_id>
@bb /pack    <session_id>
```

### Option B — MCP server (experimental)

> Requires VS Code with GitHub Copilot Chat and experimental MCP support enabled.

**Step 1:** Run the install helper:

```bash
bb wrapper install --client copilot
```

This writes the correct block to your VS Code `settings.json`:

```json
{
  "github.copilot.chat.experimental.mcp": {
    "servers": {
      "briefbridge": {
        "command": "bb-mcp",
        "args": [],
        "type": "stdio"
      }
    }
  }
}
```

**Step 2:** Restart VS Code. Copilot Chat will now have access to all 5 BriefBridge tools.

---

## Claude Code

### Step 1 — Install slash commands

```bash
bb wrapper install --client claude
```

This creates `~/.claude/commands/bb/` with `sessions.md`, `inspect.md`, `pack.md`, `use.md`, and `search.md`.

Restart Claude Code and use:

```
/bb:sessions
/bb:inspect <session_id>
/bb:pack    <session_id>
/bb:use     <session_id>
/bb:search  <query>
```

### Step 2 — Add MCP server (optional but recommended)

Add to `~/.claude.json` (or your project's `.claude/settings.json`):

```json
{
  "mcpServers": {
    "briefbridge": {
      "command": "bb-mcp",
      "args": []
    }
  }
}
```

When MCP is configured, Claude Code calls the tools directly — no shell commands needed.

---

## Codex

### Step 1 — Install the skill

```bash
bb wrapper install --client codex
```

This creates the `briefbridge` skill at `~/.agents/skills/briefbridge/SKILL.md`.

Restart Codex. Type `$briefbridge` in the composer to activate it, or ask about sessions naturally — Codex will activate the skill automatically.

### Step 2 — Add MCP server (optional but recommended)

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.briefbridge]
command = "bb-mcp"
args    = []
```

When MCP is configured, Codex calls the tools directly instead of running shell commands.

---

## CLI Reference

```bash
# List sessions
bb sessions                        # all recent sessions
bb sessions --last 24h             # last 24 hours
bb sessions --last 7d              # last 7 days
bb sessions --provider claude      # filter: copilot | claude | codex
bb sessions --repo auto            # filter by current git repo
bb sessions --json                 # JSON output

# Inspect
bb inspect <session_id>
bb inspect <session_id> --json

# Handoff pack
bb pack <session_id>
bb pack <session_id> --json

# Paste-ready context block
bb use <session_id>                        # compact (default)
bb use <session_id> --mode full            # everything
bb use <session_id> --mode goal,files,errors  # combine sections

# Export to file
bb export <session_id> --format json
bb export <session_id> --format md

# Search within a session
bb ask <session_id> "what errors did we hit?"

# Install wrappers
bb wrapper install                 # all clients
bb wrapper install --client claude
bb wrapper install --client codex
bb wrapper install --client copilot

# MCP server
bb-mcp                             # start STDIO MCP server
bb mcp                             # same, via bb CLI
```

### Context modes for `bb use`

| Mode | What you get |
|---|---|
| `summary` | One-paragraph overview |
| `goal` | Objective only |
| `hypothesis` | Main hypothesis only |
| `files` | Files touched with inferred roles |
| `errors` | Errors with log excerpts |
| `commands` | Commands run with exit codes |
| `decisions` | Decisions made with confidence level |
| `todos` | Pending items with priority |
| `compact` | goal + hypothesis + top files + errors + todos *(default)* |
| `full` | Everything |

---

## MCP Tools Reference

BriefBridge exposes 5 tools over the MCP protocol (STDIO transport).
Register `bb-mcp` as an MCP server in any MCP-compatible client.

### `bb_sessions_list`

```json
Input:  { "hours": 24, "repo": "auto", "provider": "any" }
Output: { "sessions": [{ "id", "provider", "time", "repo", "files_count", "title", "status" }] }
```

### `bb_session_inspect`

```json
Input:  { "session_id": "codex:019cdf99" }
Output: { "id", "provider", "repo", "branch", "objective", "main_hypothesis",
          "relevant_files", "errors_found", "important_commands",
          "decisions_made", "pending_items" }
```

### `bb_session_pack`

```json
Input:  { "session_id": "...", "mode": "compact" }
Output: { "handoff_id", "markdown", "plain_text", "json": { ... } }
```

### `bb_session_use`

```json
Input:  { "session_id": "...", "mode": "compact" }
Output: { "context_block": "ready-to-paste string" }
```

### `bb_session_search`

```json
Input:  { "query": "login bug", "hours": 72, "provider": "any", "repo": null }
Output: { "matches": [{ "session_id", "provider", "score", "snippet" }] }
```

---

## Development

```bash
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# MCP server tests
pytest tests/test_mcp_server.py -v

# Wrapper tests
pytest tests/test_wrappers/ -v
```

### Project conventions

- Python 3.12+, Pydantic v2, Typer, Rich, FastMCP (`mcp` SDK)
- No external API calls — everything is local file parsing
- Adapters return empty / best-effort results when provider data is missing
- All terminal output uses `sys.stdout.buffer` with explicit UTF-8 encoding for Windows compatibility

### Adding a new provider

1. Add an adapter in `src/briefbridge/adapters/<provider>.py` implementing `BaseAdapter`
2. Register it in `src/briefbridge/adapters/registry.py`
3. Add fixtures in `tests/fixtures/<provider>/`
4. Add adapter tests in `tests/test_adapters/test_<provider>.py`

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

Made with ☕ by [TiagoSchr](https://github.com/TiagoSchr)

</div>
