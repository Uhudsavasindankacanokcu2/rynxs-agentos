"""
Checkpoint commands: create, verify
"""

import sys
import json
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

# Add engine to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from engine.log import FileEventStore
from engine.core import Reducer
from engine.replay import replay
from engine.checkpoint import Checkpoint, CheckpointStore
from engine.checkpoint.snapshot import serialize_state, compute_state_hash
from engine.checkpoint.signer import SigningKey, VerifyingKey
from engine.checkpoint.verify import verify_signature, verify_full

app = typer.Typer()
console = Console()


@app.command()
def create(
    log_path: str = typer.Option(
        "/tmp/rynxs-logs/operator-events.log",
        "--log",
        "-l",
        help="Path to event log file",
    ),
    output: str = typer.Option(
        None,
        "--out",
        "-o",
        help="Output checkpoint file (default: auto-generated)",
    ),
    key_path: Optional[str] = typer.Option(
        None,
        "--key",
        "-k",
        help="Path to signing key (Ed25519 private key PEM)",
    ),
    generate_key: bool = typer.Option(
        False,
        "--generate-key",
        help="Generate new signing key if not provided",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Create signed checkpoint from event log.

    Examples:
        rynxs checkpoint create
        rynxs checkpoint create --out checkpoint.json
        rynxs checkpoint create --key signing_key.pem
        rynxs checkpoint create --generate-key
    """
    try:
        # Load event store
        store = FileEventStore(log_path)

        # Setup reducer (MVP - minimal handlers)
        reducer = Reducer()

        def handle_agent_observed(cur, ev):
            cur = cur or {}
            cur[ev.payload["name"]] = ev.payload.get("spec_hash", "")
            return cur

        def handle_actions_decided(cur, ev):
            return cur

        def handle_action_applied(cur, ev):
            return cur

        reducer.register("AgentObserved", handle_agent_observed)
        reducer.register("ActionsDecided", handle_actions_decided)
        reducer.register("ActionApplied", handle_action_applied)

        # Replay to get state
        if not json_output:
            console.print("[bold]Replaying event log to create checkpoint...[/bold]")

        result = replay(store, reducer)
        state = result.state

        # Get last event (read raw JSON to get hash/seq)
        events_data = []
        with open(log_path, "r") as f:
            for idx, line in enumerate(f):
                if not line.strip():
                    continue
                rec = json.loads(line)
                rec["seq"] = idx
                events_data.append(rec)

        if not events_data:
            if json_output:
                print(json.dumps({"error": "Event log is empty"}))
            else:
                console.print("[red]Error: Event log is empty[/red]")
            raise typer.Exit(1)

        last_event_rec = events_data[-1]

        # Load or generate signing key
        if key_path:
            signing_key = SigningKey.load_pem(key_path)
        elif generate_key:
            signing_key = SigningKey.generate()
            if not json_output:
                console.print(f"[yellow]Generated new signing key[/yellow]")
        else:
            # Generate ephemeral key
            signing_key = SigningKey.generate()
            if not json_output:
                console.print(
                    "[yellow]Warning: Using ephemeral key (use --key or --generate-key for persistent key)[/yellow]"
                )

        # Create checkpoint manually
        import base64
        from engine.checkpoint.snapshot import serialize_state, compute_state_hash

        state_bytes = serialize_state(state)
        state_hash = compute_state_hash(state)
        state_bytes_b64 = base64.b64encode(state_bytes).decode("ascii")

        # Build checkpoint payload for signing
        checkpoint_payload = {
            "version": 1,
            "event_index": last_event_rec["seq"],
            "event_hash": last_event_rec.get("event_hash", ""),
            "state_hash": state_hash,
            "state_bytes": state_bytes_b64,
            "created_at_logical": last_event_rec["event"].get("ts", 0),
            "pubkey_id": signing_key.get_pubkey_id(),
            "meta": {"cli_version": "0.1.0", "source": "rynxs checkpoint create"},
        }

        # Sign checkpoint
        signature = signing_key.sign_base64(checkpoint_payload)

        # Create Checkpoint object
        checkpoint = Checkpoint(
            version=checkpoint_payload["version"],
            event_index=checkpoint_payload["event_index"],
            event_hash=checkpoint_payload["event_hash"],
            state_hash=checkpoint_payload["state_hash"],
            state_bytes=checkpoint_payload["state_bytes"],
            created_at_logical=checkpoint_payload["created_at_logical"],
            pubkey_id=checkpoint_payload["pubkey_id"],
            signature=signature,
            meta=checkpoint_payload["meta"],
        )

        # Save checkpoint
        if output:
            # Manual save to specified path
            with open(output, "w") as f:
                json.dump(checkpoint.to_dict(), f, indent=2)
            checkpoint_path = output
        else:
            # Auto-generate filename via CheckpointStore
            checkpoint_store = CheckpointStore(".")
            checkpoint_path = checkpoint_store.save(checkpoint)

        if json_output:
            print(
                json.dumps(
                    {
                        "success": True,
                        "checkpoint_path": checkpoint_path,
                        "event_index": checkpoint.event_index,
                        "event_hash": checkpoint.event_hash,
                        "state_hash": checkpoint.state_hash,
                        "pubkey_id": checkpoint.pubkey_id,
                    },
                    indent=2,
                )
            )
        else:
            console.print(f"[green]✓ Checkpoint created successfully[/green]")
            console.print(f"  File: [cyan]{checkpoint_path}[/cyan]")
            console.print(f"  Event index: {checkpoint.event_index}")
            console.print(f"  Event hash: {checkpoint.event_hash[:16]}...")
            console.print(f"  State hash: {checkpoint.state_hash[:16]}...")
            console.print(f"  Public key ID: {checkpoint.pubkey_id}")

        raise typer.Exit(0)

    except FileNotFoundError as e:
        if json_output:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)
    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)


@app.command()
def verify(
    checkpoint_path: str = typer.Argument(..., help="Path to checkpoint file"),
    log_path: str = typer.Option(
        "/tmp/rynxs-logs/operator-events.log",
        "--log",
        "-l",
        help="Path to event log file",
    ),
    key_path: Optional[str] = typer.Option(
        None,
        "--key",
        "-k",
        help="Path to verifying key (Ed25519 public key PEM)",
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Full verification (signature + event hash + state replay)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Verify checkpoint signature and integrity.

    Examples:
        rynxs checkpoint verify checkpoint.json
        rynxs checkpoint verify checkpoint.json --full
        rynxs checkpoint verify checkpoint.json --key verifying_key.pem
    """
    try:
        # Load checkpoint
        checkpoint_store = CheckpointStore(".")
        checkpoint = checkpoint_store.load(checkpoint_path)

        # Load verifying key
        if key_path:
            verifying_key = VerifyingKey.load_pem(key_path)
        else:
            # Try to extract from checkpoint metadata (if available)
            if not json_output:
                console.print(
                    "[yellow]Warning: No verifying key provided, signature verification skipped[/yellow]"
                )
            verifying_key = None

        if full and not verifying_key:
            if json_output:
                print(json.dumps({"error": "Full verification requires verifying key (--key)"}))
            else:
                console.print(
                    "[red]Error: Full verification requires verifying key (--key)[/red]"
                )
            raise typer.Exit(1)

        # Verify
        if not json_output:
            console.print("[bold]Verifying checkpoint...[/bold]")

        if full:
            # Full verification
            store = FileEventStore(log_path)
            reducer = Reducer()

            # Register handlers
            def handle_agent_observed(cur, ev):
                cur = cur or {}
                cur[ev.payload["name"]] = ev.payload.get("spec_hash", "")
                return cur

            def handle_actions_decided(cur, ev):
                return cur

            def handle_action_applied(cur, ev):
                return cur

            reducer.register("AgentObserved", handle_agent_observed)
            reducer.register("ActionsDecided", handle_actions_decided)
            reducer.register("ActionApplied", handle_action_applied)

            verify_full(checkpoint, verifying_key, store, reducer)

            if json_output:
                print(
                    json.dumps(
                        {
                            "success": True,
                            "verification": "full",
                            "signature": "valid",
                            "state_hash": "match",
                            "event_hash": "match",
                            "replay": "consistent",
                        }
                    )
                )
            else:
                console.print("[green]✓ Full verification passed[/green]")
                console.print("  [green]✓[/green] Signature valid")
                console.print("  [green]✓[/green] State hash match")
                console.print("  [green]✓[/green] Event hash match")
                console.print("  [green]✓[/green] Replay consistent")
        else:
            # Signature-only verification
            if verifying_key:
                verify_signature(checkpoint, verifying_key)
                if json_output:
                    print(json.dumps({"success": True, "verification": "signature", "signature": "valid"}))
                else:
                    console.print("[green]✓ Signature verification passed[/green]")
            else:
                # No verification possible
                if json_output:
                    print(json.dumps({"success": True, "verification": "none", "message": "No verifying key provided"}))
                else:
                    console.print("[yellow]No verification performed (no key provided)[/yellow]")

        raise typer.Exit(0)

    except FileNotFoundError as e:
        if json_output:
            print(json.dumps({"error": "File not found", "details": str(e)}))
        else:
            console.print(f"[red]Error: File not found:[/red] {e}")
        raise typer.Exit(2)
    except Exception as e:
        if json_output:
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            console.print(f"[red]Verification failed:[/red] {e}")
        raise typer.Exit(1)
