"""Example: full end-to-end flow using the MCP server tools directly.

This script demonstrates the complete BriefBridge handoff workflow:
1. List sessions from all providers
2. Inspect a session
3. Generate a handoff pack
4. Get a paste-ready context block

Run with: python examples/full_flow_example.py
"""

from __future__ import annotations

import json
import subprocess
import sys


def run_bb(*args: str) -> dict | str:
    """Run a bb CLI command and return parsed JSON or raw string."""
    result = subprocess.run(
        ["bb", *args],
        capture_output=True,
        timeout=30,
    )
    stdout = result.stdout.decode("utf-8").strip()
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return stdout


def main() -> None:
    print("=" * 60)
    print("BriefBridge End-to-End Flow Example")
    print("=" * 60)

    # ---- Step 1: List sessions ----
    print("\n📋 Step 1: List recent sessions (last 24h)")
    sessions_data = run_bb("sessions", "--json", "--last", "24h")
    if isinstance(sessions_data, str):
        print(f"  ⚠ Could not parse sessions: {sessions_data[:100]}")
        return

    sessions = sessions_data if isinstance(sessions_data, list) else []
    print(f"  Found {len(sessions)} sessions")
    for s in sessions[:5]:
        print(f"  - [{s.get('provider', '?')}] {s.get('id', '?')} — {s.get('title', 'no title')}")

    if not sessions:
        print("\n  No sessions found. Run some coding sessions first!")
        return

    # ---- Step 2: Pick most recent session ----
    session_id = sessions[0]["id"]
    provider = sessions[0].get("provider", "?")
    print(f"\n🔍 Step 2: Inspect session [{provider}] {session_id}")

    inspect_data = run_bb("inspect", session_id, "--json")
    if isinstance(inspect_data, dict):
        print(f"  Repo: {inspect_data.get('repo_name', 'unknown')}")
        print(f"  Branch: {inspect_data.get('branch', 'unknown')}")
        files = inspect_data.get('files_touched', [])
        print(f"  Files touched: {len(files)}")
        errors = inspect_data.get('error_hints', [])
        print(f"  Error hints: {len(errors)}")
    else:
        print(f"  Raw: {inspect_data[:200]}")

    # ---- Step 3: Generate handoff pack ----
    print(f"\n📦 Step 3: Generate handoff pack for {session_id}")
    pack_result = run_bb("pack", session_id, "--json")
    if isinstance(pack_result, dict):
        print(f"  Handoff ID: {pack_result.get('handoff_id', '?')}")
        print(f"  Objective: {pack_result.get('objective', 'not inferred')}")
        print(f"  Files: {len(pack_result.get('relevant_files', []))}")
        print(f"  Errors: {len(pack_result.get('errors_found', []))}")
        print(f"  Decisions: {len(pack_result.get('decisions_made', []))}")
        print(f"  Pending: {len(pack_result.get('pending_items', []))}")
    else:
        print(f"  Raw: {str(pack_result)[:200]}")

    # ---- Step 4: Generate paste-ready context block ----
    print(f"\n📋 Step 4: Generate context block (compact mode)")
    context = run_bb("use", session_id, "--mode", "compact")
    if isinstance(context, str):
        print("  Context block (first 400 chars):")
        print("  " + "-" * 40)
        for line in context[:400].splitlines():
            print(f"  {line}")
        print("  " + "-" * 40)
        print("\n  ✓ Copy this block and paste into Claude Code, Copilot, or Codex!")
    else:
        print(f"  {context}")

    print("\n" + "=" * 60)
    print("Done! To continue in another agent, paste the context block above.")
    print("=" * 60)


if __name__ == "__main__":
    main()
