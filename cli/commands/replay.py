"""
Replay command: Replay event log and verify state
"""

import sys
import json
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

# Add engine to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from engine.log import FileEventStore
from engine.core import Reducer
from engine.replay import replay as replay_events
from engine.checkpoint.snapshot import compute_state_hash

console = Console()


def replay_command(
    log_path: str = typer.Option(
        "/tmp/rynxs-logs/operator-events.log",
        "--log",
        "-l",
        help="Path to event log file",
    ),
    until: Optional[int] = typer.Option(None, "--until", "-u", help="Replay until sequence number"),
    show_state: bool = typer.Option(False, "--show-state", "-s", help="Show final state"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Replay event log and verify state reconstruction.

    Examples:
        rynxs replay
        rynxs replay --until 10
        rynxs replay --show-state
        rynxs replay --json
    """
    try:
        store = FileEventStore(log_path)
        reducer = Reducer()

        # Register minimal handlers (MVP - just track events)
        def handle_agent_observed(cur, ev):
            cur = cur or {}
            cur[ev.payload["name"]] = ev.payload.get("spec_hash", "")
            return cur

        def handle_actions_decided(cur, ev):
            return cur  # No state change

        def handle_action_applied(cur, ev):
            return cur  # No state change

        reducer.register("AgentObserved", handle_agent_observed)
        reducer.register("ActionsDecided", handle_actions_decided)
        reducer.register("ActionApplied", handle_action_applied)

        # Replay
        if not json_output:
            console.print("[bold]Replaying event log...[/bold]")

        result = replay_events(store, reducer)
        state_hash = compute_state_hash(result.state)

        # Count event types
        event_types = {}
        for event in store.read(from_seq=0):
            if until is not None and event.seq > until:
                break
            event_types[event.type] = event_types.get(event.type, 0) + 1

        if json_output:
            # JSON output
            output = {
                "success": True,
                "events_replayed": result.applied,
                "state_version": result.state.version,
                "state_hash": state_hash,
                "event_counts": event_types,
            }
            if show_state:
                output["state_aggregates"] = result.state.aggregates
            print(json.dumps(output, indent=2))
        else:
            # Rich output
            console.print(f"[green]✓ Replayed {result.applied} events successfully[/green]")
            console.print(f"  State version: [cyan]{result.state.version}[/cyan]")
            console.print(f"  State hash: [yellow]{state_hash}[/yellow]")

            # Event counts table
            table = Table(title="Event Counts")
            table.add_column("Event Type", style="green")
            table.add_column("Count", style="cyan", justify="right")

            for event_type in sorted(event_types.keys()):
                table.add_row(event_type, str(event_types[event_type]))

            console.print(table)

            if show_state:
                console.print("\n[bold]Final State Aggregates:[/bold]")
                syntax_str = json.dumps(result.state.aggregates, indent=2)
                from rich.syntax import Syntax

                syntax = Syntax(syntax_str, "json", theme="monokai")
                console.print(syntax)

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
