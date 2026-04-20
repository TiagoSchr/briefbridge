"""BriefBridge CLI — Cross-agent session handoff for coding tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from briefbridge.config import BriefBridgeConfig
from briefbridge.models.enums import ImportMode
from briefbridge.storage.sqlite import StorageBackend

app = typer.Typer(
    name="briefbridge",
    help="Cross-agent session handoff for coding tools.",
    no_args_is_help=True,
)

console = Console()
err_console = Console(stderr=True)


def _print_json(text: str) -> None:
    """Print raw text to stdout, bypassing Rich and handling Windows encoding."""
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


# Global state
_config: BriefBridgeConfig | None = None
_storage: StorageBackend | None = None


def _get_config() -> BriefBridgeConfig:
    global _config
    if _config is None:
        _config = BriefBridgeConfig.load()
    return _config


def _get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        cfg = _get_config()
        cfg.ensure_data_dir()
        _storage = StorageBackend(cfg.db_path)
    return _storage


def _parse_last(last: str | None) -> float | None:
    """Parse a time window like '24h', '7d', '30m' into hours."""
    if not last:
        return None
    last = last.strip().lower()
    if last.endswith("h"):
        return float(last[:-1])
    if last.endswith("d"):
        return float(last[:-1]) * 24
    if last.endswith("m"):
        return float(last[:-1]) / 60
    # Assume hours
    try:
        return float(last)
    except ValueError:
        err_console.print(f"[red]Invalid time window: {last}[/red]")
        raise typer.Exit(1)


# ------------------------------------------------------------------
# sessions
# ------------------------------------------------------------------


@app.command()
def sessions(
    last: Annotated[
        Optional[str],
        typer.Option("--last", help="Time window, e.g. '24h', '7d', '30m'"),
    ] = None,
    repo: Annotated[
        Optional[str],
        typer.Option("--repo", help="Filter by repo path or 'auto' for cwd"),
    ] = None,
    branch: Annotated[
        Optional[str],
        typer.Option("--branch", help="Filter by branch name"),
    ] = None,
    provider: Annotated[
        Optional[str],
        typer.Option("--provider", help="Filter by provider: codex, claude, copilot"),
    ] = None,
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """List recent sessions from all available providers."""
    from briefbridge.services.sessions import SessionsService

    svc = SessionsService(config=_get_config(), storage=_get_storage())
    results = svc.list_sessions(
        last_hours=_parse_last(last),
        repo=repo,
        branch=branch,
        provider=provider,  # type: ignore[arg-type]
    )

    if output_json:
        data = [
            {
                "id": s.id,
                "provider": s.provider,
                "started_at": s.started_at,
                "repo_name": s.repo_name,
                "branch": s.branch,
                "title": s.title,
                "files_touched": len(s.files_touched),
            }
            for s in results
        ]
        _print_json(json.dumps(data, indent=2, default=str))
        return

    if not results:
        err_console.print("[yellow]No sessions found.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Sessions", show_lines=False)
    table.add_column("ID", style="cyan", no_wrap=True, max_width=40)
    table.add_column("Provider", style="magenta")
    table.add_column("Time", style="green")
    table.add_column("Repo", style="blue")
    table.add_column("Branch")
    table.add_column("Title", max_width=50)
    table.add_column("Files", justify="right")

    for s in results:
        time_str = s.started_at[:16] if s.started_at else "-"
        table.add_row(
            s.id,
            s.provider,
            time_str,
            s.repo_name or "-",
            s.branch or "-",
            (s.title or "-")[:50],
            str(len(s.files_touched)),
        )

    console.print(table)


# ------------------------------------------------------------------
# inspect
# ------------------------------------------------------------------


@app.command()
def inspect(
    session_id: Annotated[str, typer.Argument(help="Session ID to inspect")],
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Show detailed information about a session."""
    from briefbridge.services.sessions import SessionsService

    svc = SessionsService(config=_get_config(), storage=_get_storage())
    try:
        detail = svc.inspect_session(session_id)
    except FileNotFoundError:
        err_console.print(f"[red]Session not found: {session_id}[/red]")
        raise typer.Exit(1)

    if output_json:
        data = {
            "id": detail.id,
            "provider": detail.provider,
            "started_at": detail.started_at.isoformat() if detail.started_at else None,
            "ended_at": detail.ended_at.isoformat() if detail.ended_at else None,
            "repo_path": detail.repo_path,
            "repo_name": detail.repo_name,
            "branch": detail.branch,
            "title": detail.title,
            "files_touched": detail.files_touched,
            "message_count": detail.message_count,
            "command_count": detail.command_count,
            "error_hints": detail.error_hints,
            "first_user_message": detail.first_user_message,
        }
        _print_json(json.dumps(data, indent=2, default=str))
        return

    console.print(f"\n[bold cyan]Session:[/bold cyan] {detail.id}")
    console.print(f"[bold]Provider:[/bold] {detail.provider}")
    if detail.started_at:
        console.print(f"[bold]Started:[/bold] {detail.started_at.isoformat()}")
    if detail.ended_at:
        console.print(f"[bold]Ended:[/bold] {detail.ended_at.isoformat()}")
    if detail.repo_name:
        console.print(f"[bold]Repo:[/bold] {detail.repo_name}")
    if detail.branch:
        console.print(f"[bold]Branch:[/bold] {detail.branch}")
    if detail.title:
        console.print(f"[bold]Title:[/bold] {detail.title}")
    console.print(f"[bold]Messages:[/bold] {detail.message_count}")
    console.print(f"[bold]Commands:[/bold] {detail.command_count}")

    if detail.first_user_message:
        console.print(f"\n[bold]First user message:[/bold]")
        console.print(f"  {detail.first_user_message}")

    if detail.files_touched:
        console.print(f"\n[bold]Files touched:[/bold]")
        for f in detail.files_touched[:20]:
            console.print(f"  - {f}")

    if detail.error_hints:
        console.print(f"\n[bold red]Errors:[/bold red]")
        for e in detail.error_hints[:10]:
            console.print(f"  {e}")


# ------------------------------------------------------------------
# pack
# ------------------------------------------------------------------


@app.command()
def pack(
    session_id: Annotated[str, typer.Argument(help="Session ID to pack")],
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Generate a handoff pack for a session."""
    from briefbridge.services.handoff import HandoffService

    svc = HandoffService(config=_get_config(), storage=_get_storage())
    try:
        result = svc.generate_pack(session_id)
    except FileNotFoundError:
        err_console.print(f"[red]Session not found: {session_id}[/red]")
        raise typer.Exit(1)

    if output_json:
        from briefbridge.render.json_export import render_json

        _print_json(render_json(result))
        return

    console.print(f"\n[bold green]✓ Handoff pack generated[/bold green]")
    console.print(f"  [bold]ID:[/bold] {result.handoff_id}")
    console.print(f"  [bold]Provider:[/bold] {result.source_provider}")
    console.print(f"  [bold]Session:[/bold] {result.source_session_id}")
    if result.objective:
        console.print(f"  [bold]Objective:[/bold] {result.objective}")
    console.print(f"  [bold]Files:[/bold] {len(result.relevant_files)}")
    console.print(f"  [bold]Errors:[/bold] {len(result.errors_found)}")
    console.print(f"  [bold]Commands:[/bold] {len(result.important_commands)}")
    console.print(f"  [bold]Decisions:[/bold] {len(result.decisions_made)}")
    console.print(f"  [bold]Pending:[/bold] {len(result.pending_items)}")
    console.print(f"\n  Use `bb export {session_id}` to save as file.")
    console.print(f"  Use `bb use {session_id} --mode compact` to get a paste-ready block.")


# ------------------------------------------------------------------
# use
# ------------------------------------------------------------------


@app.command()
def use(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="Import mode(s), comma-separated"),
    ] = "summary",
) -> None:
    """Generate a context block ready to paste into another agent."""
    from briefbridge.services.handoff import HandoffService

    # Parse comma-separated modes
    mode_names = [m.strip().lower() for m in mode.split(",")]
    modes: list[ImportMode] = []
    for name in mode_names:
        try:
            modes.append(ImportMode(name))
        except ValueError:
            valid = ", ".join(m.value for m in ImportMode)
            err_console.print(f"[red]Unknown mode: {name}. Valid: {valid}[/red]")
            raise typer.Exit(1)

    svc = HandoffService(config=_get_config(), storage=_get_storage())
    try:
        output = svc.use_pack(session_id, modes)
    except FileNotFoundError:
        err_console.print(f"[red]Session not found: {session_id}[/red]")
        raise typer.Exit(1)

    # Print raw to stdout (no rich formatting — designed for piping)
    sys.stdout.write(output + "\n")


# ------------------------------------------------------------------
# ask
# ------------------------------------------------------------------


@app.command()
def ask(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    question: Annotated[str, typer.Argument(help="Question about the session")],
) -> None:
    """Ask a question about a session (local keyword search)."""
    from briefbridge.services.search import SearchService

    svc = SearchService(config=_get_config(), storage=_get_storage())
    result = svc.ask(session_id, question)
    console.print(result)


# ------------------------------------------------------------------
# export
# ------------------------------------------------------------------


@app.command()
def export(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Export format: json or md"),
    ] = "json",
    output_dir: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output directory"),
    ] = None,
) -> None:
    """Export a handoff pack to a file."""
    from briefbridge.services.handoff import HandoffService

    if fmt not in ("json", "md"):
        err_console.print(f"[red]Unsupported format: {fmt}. Use 'json' or 'md'.[/red]")
        raise typer.Exit(1)

    out_path = Path(output_dir) if output_dir else None
    svc = HandoffService(config=_get_config(), storage=_get_storage())

    try:
        path = svc.export_pack(session_id, fmt=fmt, output_dir=out_path)
    except FileNotFoundError:
        err_console.print(f"[red]Session not found: {session_id}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Exported to:[/green] {path}")


# ------------------------------------------------------------------
# wrapper — install UX wrappers for each client
# ------------------------------------------------------------------


@app.command()
def wrapper(
    action: Annotated[
        str,
        typer.Argument(help="Action: install or uninstall"),
    ] = "install",
    client: Annotated[
        str,
        typer.Option("--client", "-c", help="Client: claude, codex, or copilot (default: all)"),
    ] = "all",
) -> None:
    """Install or uninstall BriefBridge UX wrappers for each client."""
    clients = ["claude", "codex", "copilot"] if client == "all" else [client.lower()]

    for c in clients:
        if c == "claude":
            from briefbridge.wrappers.claude import install as claude_install, uninstall as claude_uninstall
            console.print(f"\n[bold]Claude Code[/bold] ({action}):")
            if action == "install":
                claude_install()
                console.print("[green]→ Add the MCP server to Claude Code settings:[/green]")
                from briefbridge.wrappers.claude import print_mcp_config
                print_mcp_config()
            else:
                from briefbridge.wrappers.claude import uninstall as claude_uninstall
                claude_uninstall()

        elif c == "codex":
            from briefbridge.wrappers.codex import install as codex_install
            console.print(f"\n[bold]Codex[/bold] ({action}):")
            if action == "install":
                codex_install()
            else:
                from briefbridge.wrappers.codex import uninstall as codex_uninstall
                codex_uninstall()

        elif c == "copilot":
            console.print(f"\n[bold]GitHub Copilot[/bold] ({action}):")
            if action == "install":
                from briefbridge.wrappers.copilot import print_vscode_settings
                console.print("[green]→ Add to VS Code settings.json:[/green]")
                print_vscode_settings()
            else:
                console.print("[yellow]Nothing to uninstall — remove the MCP block from settings.json manually.[/yellow]")

        else:
            err_console.print(f"[red]Unknown client: {c}. Use: claude, codex, copilot, all[/red]")


# ------------------------------------------------------------------
# mcp — run the MCP server
# ------------------------------------------------------------------


@app.command(name="mcp")
def mcp_command() -> None:
    """Start the BriefBridge MCP server (STDIO transport)."""
    from briefbridge.mcp_server import main
    main()


if __name__ == "__main__":
    app()
