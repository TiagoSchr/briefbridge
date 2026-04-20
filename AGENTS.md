# BriefBridge — Agent Instructions

Cross-agent session handoff for coding tools.
This file is read by Claude Code, GitHub Copilot, Codex, Cursor, and Continue.

## Project Overview

BriefBridge reads local session data from Claude Code, GitHub Copilot Chat,
and OpenAI Codex, then extracts structured handoff packs that can be pasted
into any other coding agent to continue work seamlessly.

## Architecture

```
src/briefbridge/
├── adapters/       # One adapter per provider (claude, codex, copilot)
├── extract/        # Deterministic + heuristic extraction
├── ingest/         # IngestManager routes to correct adapter
├── models/         # Pydantic models (HandoffPack, RawSession, etc.)
├── render/         # JSON, Markdown, plain-text output
├── services/       # Business logic (sessions, handoff, search)
├── storage/        # SQLite FTS5 cache
├── config.py       # BriefBridgeConfig
└── cli.py          # Typer CLI — entry points: bb, briefbridge
```

VS Code extension: `vscode-ext/` — chat participant `@bb`

## Key Commands

```bash
bb sessions                           # list all sessions
bb sessions --provider claude         # filter by provider
bb inspect <session_id>               # session details
bb pack <session_id>                  # generate handoff pack
bb use <session_id> --mode compact    # paste-ready block
bb export <session_id> --format json  # save to file
```

## Development

```bash
pip install -e ".[dev]"     # install in dev mode
pytest tests/ -v            # run 81 tests
```

## Conventions

- Python 3.12+, Pydantic v2, Typer for CLI
- Each adapter handles one provider's local file format
- Adapters must implement `BaseAdapter` (discover_sessions, read_session)
- Tests use mock fixtures in `tests/fixtures/`
- No external API calls — everything is local file parsing

## Context Lens (token optimization)

This project has Context Lens installed. Before reading files, call:

```
lens_context(query="<your task>", task="auto")
```

This returns optimized context (75-95% smaller than raw files).
Only read files directly if they are not covered by the context block.
