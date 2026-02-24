
import os
import json
import time
import random
import sys
import traceback
from typing import Optional, Dict, Any

from .policy import UniversePolicy
from .workspace import Workspace
from .providers.local_openai_compat import LocalOpenAICompat
from .tools.registry import ToolRegistry
from .tools.runner import ToolRunner
from .models import Consciousness
from .tools.audit import write_audit as original_write_audit
from .controllers import (
    EntityLifecycle,
    ZoneController,
    PhysicsJitterController,
    LuckController,
    SleepController,
)


def load_agent_spec() -> dict:
    with open("agent.json", "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    """
    Main entrypoint for the agent runtime.
    Orchestrates the agent's lifecycle, including setup, main loop, and shutdown.
    """
    agent_name = os.getenv("AGENT_NAME", "agent")
    namespace = os.getenv("AGENT_NAMESPACE", "universe")
    run_id = os.getenv("RUN_ID", "default-run")
    
    workspace = Workspace("workspace")
    # Ensure workspace exists at the very beginning
    workspace.path("").mkdir(parents=True, exist_ok=True)

    def write_crash_log(exc: Exception):
        """Logs critical errors to a dedicated crash log file and stderr."""
        crash_log_path = workspace.path("crash.log")
        error_message = f"--- CRITICAL RUNTIME ERROR ---\n"
        error_message += f"Timestamp: {time.time()}\n"
        error_message += f"Agent: {agent_name}, Run ID: {run_id}\n"
        error_message += f"Exception: {exc}\n"
        error_message += traceback.format_exc()
        
        try:
            with open(crash_log_path, "a", encoding="utf-8") as f:
                f.write(error_message + "\n")
            print(f"CRITICAL: Runtime error. Details logged to {crash_log_path}", flush=True, file=sys.stderr)
        except Exception as log_exc:
            # If logging itself fails, print to stderr as a last resort.
            print(f"FATAL: Could not write to crash.log. Original error: {error_message}", flush=True, file=sys.stderr)
            print(f"FATAL: Logging exception: {log_exc}", flush=True, file=sys.stderr)
        
        print(error_message, flush=True, file=sys.stderr)

    try:
        spec = load_agent_spec()

        # --- AUDIT & I/O-SAFE WRAPPER ---
        # Line-buffered file handle for audit trail
        audit_file_handle = open(workspace.path("audit.jsonl"), "a", buffering=1, encoding="utf-8")

        def audit(event_type: str, detail: Optional[Dict[str, Any]] = None):
            """
            A hardened audit function that writes events and ensures they are
            flushed to disk, preventing data loss from buffering.
            """
            payload = {
                "t": time.time(),
                "event": event_type,
                "agent": agent_name,
                "ns": namespace,
                "consciousness_id": consciousness.id if 'consciousness' in locals() else 'N/A',
                "run_id": run_id,
            }
            if detail:
                payload.update(detail)
            
            # Use a wrapper around the original write_audit to manage the file handle
            json.dump(payload, audit_file_handle)
            audit_file_handle.write('\n')
            audit_file_handle.flush()
            # For extreme durability (e.g., in proof mode), you might add:
            # os.fsync(audit_file_handle.fileno())

        # --- BOOT SEQUENCE ---
        audit("BOOT", {"status": "INITIALIZING", "args": sys.argv})
        print(f"[BOOT] Agent: {agent_name}, Run ID: {run_id}", flush=True)

        policy = UniversePolicy.from_agent_spec(spec)
        tools = ToolRegistry.default()
        runner = ToolRunner(workspace, policy, agent_name=agent_name, namespace=namespace)

        # Determinism Seeds
        random_seed = os.getenv("RANDOM_SEED")
        jitter_seed = os.getenv("JITTER_SEED")
        luck_seed = os.getenv("LUCK_SEED")

        # Initialize Consciousness & Controllers
        consciousness = Consciousness(
            id=os.getenv("CONSCIOUSNESS_ID", "default"),
            name=os.getenv("CONSCIOUSNESS_NAME", "Default"),
        )
        lifecycle = EntityLifecycle(workspace, consciousness)
        zones = ZoneController()
        physics = PhysicsJitterController(seed=int(jitter_seed) if jitter_seed else None)
        luck = LuckController(
            luck_rate=spec.get("macroLuckRate", 0.05),
            seed=int(luck_seed) if luck_seed else None,
        )
        sleep_ctrl = SleepController()

        # Birth sequence
        lifecycle.birth()
        
        # Replay logic for Respawn event
        state_exists = workspace.path("state/volume.json").exists()
        audit("RESPAWN" if state_exists else "BIRTH", {
            "binding_status": "ATTACHED",
            "zone_weights": {m.zone_id: m.weight for m in consciousness.state.zone_memberships},
            "epsilon_entity": physics.get_effective_jitter(consciousness),
            "restored_from": "VOLUME" if state_exists else "NONE",
            "restore_ok": True,
        })

        # --- PROVIDER INITIALIZATION (GRACEFUL) ---
        provider_cfg = spec.get("provider", {"kind": "local"})
        provider = LocalOpenAICompat(provider_cfg)
        audit("PROVIDER_INIT", {"provider_kind": provider.kind, "status": "OK" if provider.is_ready() else "DEGRADED"})


        # --- MAIN LOOP ---
        inbox = workspace.path("inbox.jsonl")
        cursor = 0
        
        # Proof mode: run a few ticks and exit cleanly
        if os.getenv("RYNXS_PROOF_MODE") == "1":
            print("[PROOF MODE] Running for 2 ticks and exiting.", flush=True)
            for _ in range(2):
                time.sleep(0.5)
                lifecycle.awake_loop()
            audit("DEATH", {"reason": "proof_mode_exit"})
            lifecycle.death()
            print("[PROOF MODE] Clean exit.", flush=True)
            sys.exit(0)

        while True:
            lifecycle.awake_loop()
            zones.update_memberships(consciousness)
            eff_jitter = physics.get_effective_jitter(consciousness)
            lifecycle.memory.ram.write("physics_jitter", eff_jitter)

            if inbox.exists():
                lines = inbox.read_text(encoding="utf-8").splitlines()
                if len(lines) > cursor:
                    new_lines = lines[cursor:]
                    cursor = len(lines)
                    for line in new_lines:
                        if not line.strip(): continue
                        msg = json.loads(line)
                        text = msg.get("text", "")
                        print(f"[INBOX] {text!r}", flush=True)

                        if provider.is_ready():
                            plan = provider.plan(text, tools.as_openai_tools())
                            results = [runner.run(c) for c in plan.get("tool_calls", [])]
                            final = provider.respond(text, results)
                            workspace.append_jsonl("outbox.jsonl", {"t": time.time(), "input": text, "plan": plan, "results": results, "output": final})
                            print("[OUT] Wrote outbox.jsonl", flush=True)
                        else:
                            print("[WARN] Provider is not ready. Skipping message processing.", flush=True)
                            audit("PROVIDER_DEGRADED", {"message_dropped": True, "text": text})

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Keyboard interrupt received. Shutting down gracefully.", flush=True)
        audit("DEATH", {"reason": "termination_request", "ram_wiped": True})
        if 'lifecycle' in locals():
            lifecycle.death()
        print("[SHUTDOWN] Cleanup complete.", flush=True)

    except Exception as e:
        # This is the "fail loudly" block for any unhandled exception.
        print(f"FATAL: An unhandled exception occurred in the main loop: {e}", flush=True, file=sys.stderr)
        write_crash_log(e)
        sys.exit(1) # Exit with a non-zero code to indicate failure

    finally:
        # Ensure files are closed on exit
        if 'audit_file_handle' in locals() and not audit_file_handle.closed:
            audit_file_handle.close()
        print("[FINAL] Runtime finished.", flush=True)

if __name__ == "__main__":
    main()
