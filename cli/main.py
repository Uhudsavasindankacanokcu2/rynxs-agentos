#!/usr/bin/env python3
"""
Rynxs CLI - Deterministic AI Workforce Orchestration

Main entrypoint for the rynxs command-line tool.
"""

import typer
from typing import Optional
from rich.console import Console
from rich.table import Table

from cli.commands import log, checkpoint, replay

# Initialize Typer app
app = typer.Typer(
    name="rynxs",
    help="Deterministic AI Workforce Orchestration CLI",
    add_completion=False,
)

# Console for rich output
console = Console()

# Add command groups
app.add_typer(log.app, name="log", help="Event log operations")
app.add_typer(checkpoint.app, name="checkpoint", help="Checkpoint management")

# Add standalone commands
app.command()(replay.replay_command)


@app.command()
def version():
    """Show version information."""
    from cli import __version__

    table = Table(show_header=False, box=None)
    table.add_row("[bold]Rynxs CLI[/bold]", f"v{__version__}")
    table.add_row("Engine", "Deterministic v2")
    table.add_row("Sprint", "D - CLI Tools")

    console.print(table)


def main():
    """Main entrypoint."""
    app()


if __name__ == "__main__":
    main()
