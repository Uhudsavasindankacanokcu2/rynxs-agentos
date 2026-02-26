"""
Event log commands: tail, inspect
"""

import sys
import json
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

# Add engine to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from engine.log import FileEventStore

app = typer.Typer()
console = Console()


@app.command()
def tail(
    log_path: str = typer.Option(
        "/tmp/rynxs-logs/operator-events.log",
        "--log",
        "-l",
        help="Path to event log file",
    ),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log file (like tail -f)"),
    lines: Optional[int] = typer.Option(None, "--lines", "-n", help="Number of lines to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Tail event log (like tail -f).

    Examples:
        rynxs log tail
        rynxs log tail --lines 10
        rynxs log tail --follow
        rynxs log tail --json
    """
    try:
        # Read raw JSON lines (to get seq/hash/prev_hash metadata)
        events_data = []
        with open(log_path, "r") as f:
            for idx, line in enumerate(f):
                if not line.strip():
                    continue
                rec = json.loads(line)
                rec["seq"] = idx  # Add sequence number
                rec["hash"] = rec.get("event_hash", "N/A")  # Normalize hash field name
                events_data.append(rec)

        if not events_data:
            if not json_output:
                console.print("[yellow]Event log is empty[/yellow]")
            else:
                print(json.dumps({"events": [], "count": 0}))
            raise typer.Exit(0)

        # Apply lines limit
        if lines:
            events_data = events_data[-lines:]

        if json_output:
            # JSON output
            print(json.dumps({"events": events_data, "count": len(events_data)}, indent=2))
        else:
            # Rich table output
            table = Table(title=f"Event Log: {log_path}")
            table.add_column("Seq", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Aggregate ID", style="yellow")
            table.add_column("Hash (prefix)", style="dim")

            for rec in events_data:
                ev = rec["event"]
                table.add_row(
                    str(rec.get("seq", "N/A")),
                    ev.get("type", "N/A"),
                    ev.get("aggregate_id", "N/A"),
                    rec.get("hash", "N/A")[:16] if rec.get("hash") else "N/A",
                )

            console.print(table)
            console.print(f"\n[bold]Total events:[/bold] {len(events_data)}")

        # TODO: Implement --follow (tail -f like behavior)
        if follow:
            console.print("\n[yellow]--follow not yet implemented[/yellow]")

        raise typer.Exit(0)

    except FileNotFoundError:
        if json_output:
            print(json.dumps({"error": "Log file not found", "path": log_path}))
        else:
            console.print(f"[red]Error: Log file not found:[/red] {log_path}")
        raise typer.Exit(2)
    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)


@app.command()
def inspect(
    log_path: str = typer.Option(
        "/tmp/rynxs-logs/operator-events.log",
        "--log",
        "-l",
        help="Path to event log file",
    ),
    from_seq: Optional[int] = typer.Option(None, "--from", help="Start from sequence number"),
    to_seq: Optional[int] = typer.Option(None, "--to", help="End at sequence number"),
    event_type: Optional[str] = typer.Option(None, "--event-type", "-t", help="Filter by event type"),
    show_payload: bool = typer.Option(False, "--payload", "-p", help="Show full payload"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Inspect event log with filters.

    Examples:
        rynxs log inspect --from 0 --to 10
        rynxs log inspect --event-type AgentObserved
        rynxs log inspect --payload --json
    """
    try:
        # Read raw JSON lines
        events_data = []
        with open(log_path, "r") as f:
            for idx, line in enumerate(f):
                if not line.strip():
                    continue
                rec = json.loads(line)
                rec["seq"] = idx  # Add sequence number
                rec["hash"] = rec.get("event_hash", "N/A")  # Normalize hash field name
                events_data.append(rec)

        # Apply filters
        if from_seq is not None:
            events_data = [rec for rec in events_data if rec.get("seq", 0) >= from_seq]
        if to_seq is not None:
            events_data = [rec for rec in events_data if rec.get("seq", 0) <= to_seq]
        if event_type:
            events_data = [rec for rec in events_data if rec["event"].get("type") == event_type]

        if not events_data:
            if not json_output:
                console.print("[yellow]No events match the filters[/yellow]")
            else:
                print(json.dumps({"events": [], "count": 0}))
            raise typer.Exit(0)

        if json_output:
            # JSON output
            if not show_payload:
                # Hide payloads
                for rec in events_data:
                    rec["event"]["payload"] = "<hidden>"
            print(json.dumps({"events": events_data, "count": len(events_data)}, indent=2))
        else:
            # Rich output
            for rec in events_data:
                ev = rec["event"]
                console.print(f"\n[bold cyan]Event {rec.get('seq', 'N/A')}[/bold cyan]")
                console.print(f"  Type: [green]{ev.get('type', 'N/A')}[/green]")
                console.print(f"  Aggregate: [yellow]{ev.get('aggregate_id', 'N/A')}[/yellow]")
                console.print(f"  Timestamp: {ev.get('ts', 'N/A')}")
                console.print(f"  Hash: {rec.get('hash', 'N/A')}")
                console.print(f"  Prev Hash: {rec.get('prev_hash', 'N/A')}")

                if show_payload:
                    console.print("  Payload:")
                    syntax = Syntax(
                        json.dumps(ev.get("payload", {}), indent=2),
                        "json",
                        theme="monokai",
                        line_numbers=False,
                    )
                    console.print(syntax)

            console.print(f"\n[bold]Total events:[/bold] {len(events_data)}")

        raise typer.Exit(0)

    except FileNotFoundError:
        if json_output:
            print(json.dumps({"error": "Log file not found", "path": log_path}))
        else:
            console.print(f"[red]Error: Log file not found:[/red] {log_path}")
        raise typer.Exit(2)
    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)
