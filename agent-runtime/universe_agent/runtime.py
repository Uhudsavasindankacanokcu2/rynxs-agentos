import os, json, time, random
from typing import Optional, Dict, Any
from .policy import UniversePolicy
from .workspace import Workspace
from .providers.local_openai_compat import LocalOpenAICompat
from .tools.registry import ToolRegistry
from .tools.runner import ToolRunner
from .models import Consciousness
from .tools.audit import write_audit
from .controllers import (
    EntityLifecycle, 
    ZoneController, 
    PhysicsJitterController, 
    LuckController, 
    SleepController
)

def load_agent_spec() -> dict:
    with open("/config/agent.json", "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    agent_name = os.getenv("AGENT_NAME", "agent")
    namespace = os.getenv("AGENT_NAMESPACE", "universe")
    run_id = os.getenv("RUN_ID", "default-run")
    spec = load_agent_spec()

    workspace = Workspace("/workspace")
    policy = UniversePolicy.from_agent_spec(spec)
    tools = ToolRegistry.default()
    runner = ToolRunner(workspace, policy, agent_name=agent_name, namespace=namespace)

    # Determinism Seeds
    random_seed = os.getenv("RANDOM_SEED")
    jitter_seed = os.getenv("JITTER_SEED")
    luck_seed = os.getenv("LUCK_SEED")

    # Initialize Consciousness from environment (Binding)
    consciousness = Consciousness(
        id=os.getenv("CONSCIOUSNESS_ID", "default"),
        name=os.getenv("CONSCIOUSNESS_NAME", "Default"),
    )
    
    # Initialize Controllers
    lifecycle = EntityLifecycle(workspace, consciousness)
    zones = ZoneController()
    physics = PhysicsJitterController(seed=int(jitter_seed) if jitter_seed else None)
    luck = LuckController(
        luck_rate=spec.get("macroLuckRate", 0.05), 
        seed=int(luck_seed) if luck_seed else None
    )
    sleep_ctrl = SleepController()
    
    # Audit helper
    def audit(event_type: str, detail: Optional[Dict[str, Any]] = None):
        payload = {
            "t": time.time(),
            "event": event_type,
            "agent": agent_name,
            "ns": namespace,
            "consciousness_id": consciousness.id,
            "run_id": run_id
        }
        if detail:
            payload.update(detail)
        write_audit(workspace, payload)


    # Birth sequence
    lifecycle.birth()
    
    # Replay logic for Respawn event
    state_exists = workspace.path("state/volume.json").exists()
    audit("RESPAWN" if state_exists else "BIRTH", {
        "binding_status": "ATTACHED",
        "zone_weights": {m.zone_id: m.weight for m in consciousness.state.zone_memberships},
        "epsilon_entity": physics.get_effective_jitter(consciousness),
        "restored_from": "VOLUME" if state_exists else "NONE",
        "restore_ok": True
    })

    provider_cfg = spec.get("provider", {"kind":"local"})
    provider = LocalOpenAICompat(provider_cfg)

    print(f"[BOOT] agent={agent_name} consciousness={consciousness.id} run_id={run_id}")

    inbox = workspace.path("inbox.jsonl")
    cursor = 0

    try:
        while True:
            # Awake dynamics
            lifecycle.awake_loop()
            
            # Periodic Dynamics Update
            zones.update_memberships(consciousness)
            eff_jitter = physics.get_effective_jitter(consciousness)
            
            # Physics exposure for proof
            lifecycle.memory.ram.write("physics_jitter", eff_jitter)
            
            # Periodic Audit of State (Every 60s approx)
            if time.time() % 60 < 0.5:
                audit("STATE_DRIFT", {
                    "zone_weights": {m.zone_id: m.weight for m in consciousness.state.zone_memberships},
                    "epsilon_entity": eff_jitter,
                    "frag_index": sleep_ctrl.calculate_fragmentation(consciousness, len(lifecycle.memory.ram.data)),
                    "stress": sleep_ctrl._estimate_stress(consciousness)
                })
            
            # Sleep trigger check
            ram_keys = len(lifecycle.memory.ram.data)
            recommendation = sleep_ctrl.get_sleep_recommendation(consciousness, ram_keys)
            
            if recommendation == "DEEP":
                sha256 = lifecycle.deep_sleep()
                sleep_ctrl.record_deep_sleep()
                audit("DEEP_SLEEP", {
                    "trigger": "Frag>T2",
                    "snapshot_path": f"/workspace/state/bucket/snap-{int(time.time())}.json",
                    "snapshot_sha256": sha256,
                    "backup_outcome": "SUCCESS"
                })
            elif recommendation == "LIGHT":
                lifecycle.light_sleep()
                audit("LIGHT_SLEEP", {"trigger": "Frag>T1", "ram_to_volume_written": True})
            
            if inbox.exists():
                lines = inbox.read_text(encoding="utf-8").splitlines()
                new = lines[cursor:]
                cursor = len(lines)
                for line in new:
                    if not line.strip():
                        continue
                    msg = json.loads(line)
                    text = msg.get("text","")
                    print(f"[INBOX] {text!r}")

                    # Luck injection
                    luck_hit = luck.apply_luck("message_processing")
                    if luck_hit:
                        audit("LUCK_APPLIED", {
                            "macroLuckRate": luck.luck_rate,
                            "luck_hit": True,
                            "luck_scope": "message_processing"
                        })

                    plan = provider.plan(text, tools.as_openai_tools())
                    results = [runner.run(c) for c in plan.get("tool_calls", [])]
                    final = provider.respond(text, results)

                    workspace.append_jsonl("outbox.jsonl", {"t": time.time(), "input": text, "plan": plan, "results": results, "output": final})
                    print("[OUT] wrote outbox.jsonl")
                    
            time.sleep(0.5)
    except KeyboardInterrupt:
        audit("DEATH", {"reason": "termination", "ram_wiped": True})
        lifecycle.death()
        print("[SHUTDOWN] ram wiped.")



if __name__ == "__main__":
    main()

