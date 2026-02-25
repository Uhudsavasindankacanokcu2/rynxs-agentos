"""
Inspect deterministic state from an event log.

Example:
  python -m engine.cli.inspect --log /path/to/operator-events.log --agent universe/agent-001
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root on path for operator reducer handlers
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.log import FileEventStore
from engine.core import Reducer
from engine.replay import replay
from engine.query import (
    list_agents,
    resolve_agent_id,
    get_agent_state,
    get_drift,
    get_failures,
)

import importlib.util

handlers_spec = importlib.util.spec_from_file_location(
    "reducer_handlers",
    str(REPO_ROOT / "operator" / "universe_operator" / "reducer_handlers.py"),
)
handlers_module = importlib.util.module_from_spec(handlers_spec)
handlers_spec.loader.exec_module(handlers_module)
register_handlers = handlers_module.register_handlers
UNIVERSE_AGG_ID = handlers_module.UNIVERSE_AGG_ID


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect deterministic operator state.")
    parser.add_argument("--log", required=True, help="Path to JSONL event log")
    parser.add_argument("--agent", help="Agent ID (namespace/name) or name")
    parser.add_argument("--at-seq", type=int, help="Replay up to sequence N (inclusive)")
    parser.add_argument("--universe-id", default=UNIVERSE_AGG_ID, help="Universe aggregate id")
    args = parser.parse_args()

    store = FileEventStore(args.log)
    reducer = Reducer(global_aggregate_id=args.universe_id)
    register_handlers(reducer)

    replay_result = replay(store, reducer, to_seq=args.at_seq)
    state = replay_result.state

    if not args.agent:
        out = {
            "universe_id": args.universe_id,
            "agents": list_agents(state, args.universe_id),
            "applied_events": replay_result.applied,
        }
        print(json.dumps(out, sort_keys=True, indent=2))
        return 0

    agent_id = resolve_agent_id(state, args.agent, args.universe_id)
    if not agent_id:
        print(f"Agent not found: {args.agent}", file=sys.stderr)
        return 2

    out = {
        "universe_id": args.universe_id,
        "agent_id": agent_id,
        "agent": get_agent_state(state, agent_id, args.universe_id),
        "drift": get_drift(state, agent_id, args.universe_id),
        "failures": get_failures(state, agent_id, last_n=20, universe_id=args.universe_id),
        "applied_events": replay_result.applied,
    }
    print(json.dumps(out, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
