"""
Generate an audit report from the event log.
"""

import argparse
import json
import sys
import hashlib
from collections import Counter
from pathlib import Path
from typing import Dict, Any, List

# Clean bootstrap for CLI output
from engine.cli._bootstrap import bootstrap

bootstrap()

from engine.log import FileEventStore
from engine.replay import replay
from engine.core import Reducer
from engine.verify import verify_actions_decided_pointers, build_decision_proof
from engine.query import list_agents, get_drift
from engine.core.state import UniverseState

from engine.log.integrity import hash_event, ZERO_HASH
from engine.core.events import Event
from engine.core.canonical import canonical_json_bytes

import importlib.util

REPO_ROOT = Path(__file__).resolve().parents[2]

handlers_spec = importlib.util.spec_from_file_location(
    "reducer_handlers",
    str(REPO_ROOT / "operator" / "universe_operator" / "reducer_handlers.py"),
)
handlers_module = importlib.util.module_from_spec(handlers_spec)
handlers_spec.loader.exec_module(handlers_module)
register_handlers = handlers_module.register_handlers
UNIVERSE_AGG_ID = handlers_module.UNIVERSE_AGG_ID


def _hash_chain_verify(log_path: str) -> Dict[str, Any]:
    prev_hash = ZERO_HASH
    checked = 0
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            ev = rec.get("event", {})
            event_obj = Event(
                type=ev.get("type"),
                aggregate_id=ev.get("aggregate_id"),
                seq=ev.get("seq"),
                ts=ev.get("ts"),
                payload=ev.get("payload", {}),
                meta=ev.get("meta", {}),
            )
            computed = hash_event(prev_hash, event_obj)
            if rec.get("prev_hash") != prev_hash:
                return {
                    "valid": False,
                    "checked": checked,
                    "error": "prev_hash mismatch",
                    "seq": event_obj.seq,
                    "expected": prev_hash,
                    "actual": rec.get("prev_hash"),
                }
            if rec.get("event_hash") != computed:
                return {
                    "valid": False,
                    "checked": checked,
                    "error": "event_hash mismatch",
                    "seq": event_obj.seq,
                    "expected": computed,
                    "actual": rec.get("event_hash"),
                }
            prev_hash = rec.get("event_hash")
            checked += 1
    return {"valid": True, "checked": checked}


def _load_checkpoint_summary(checkpoints_dir: str, pubkey_path: str = None) -> Dict[str, Any]:
    from engine.checkpoint.store import CheckpointStore
    from engine.checkpoint.model import Checkpoint

    store = CheckpointStore(checkpoints_dir)
    latest = store.find_latest()
    if not latest:
        return {"present": False}

    cp = store.load(latest)
    summary = {
        "present": True,
        "path": latest,
        "event_index": cp.event_index,
        "event_hash": cp.event_hash,
        "state_hash": cp.state_hash,
        "pubkey_id": cp.pubkey_id,
        "signature_valid": None,
        "error": None,
    }

    if not pubkey_path:
        return summary

    try:
        from engine.checkpoint.signer import VerifyingKey
        from engine.checkpoint.verify import verify_signature
    except Exception:
        summary["error"] = "signature verification skipped (cryptography not installed)"
        return summary

    key = VerifyingKey.load_from_file(pubkey_path)
    result = verify_signature(cp, key)
    summary["signature_valid"] = result.signature_valid
    summary["error"] = result.error
    return summary


def _decision_summary(log_path: str) -> Dict[str, Any]:
    actions_decided = []
    action_type_counts = Counter()
    applied = set()
    failed = set()
    actions_total = 0

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            ev = rec.get("event", {})
            etype = ev.get("type")
            payload = ev.get("payload", {}) or {}

            if etype == "ActionsDecided":
                actions_decided.append(payload)
                actions_total += len(payload.get("action_ids", []))
                for a in payload.get("actions", []):
                    action_type_counts[a.get("action_type")] += 1
            elif etype == "ActionApplied":
                aid = payload.get("action_id")
                if aid:
                    applied.add(aid)
            elif etype == "ActionFailed":
                aid = payload.get("action_id")
                if aid:
                    failed.add(aid)

    proofs = []
    for payload in actions_decided[:3]:
        action_ids = set(payload.get("action_ids", []))
        if action_ids and action_ids.issubset(applied):
            status = "applied"
        elif action_ids and (action_ids & failed):
            status = "failed"
        else:
            status = "partial"
        proofs.append(
            {
                "trigger_event_seq": payload.get("trigger_event_seq"),
                "trigger_event_hash": payload.get("trigger_event_hash"),
                "trigger_event_type": payload.get("trigger_event_type"),
                "trigger_spec_hash": payload.get("trigger_spec_hash"),
                "actions_hash": payload.get("actions_hash"),
                "action_ids": payload.get("action_ids", []),
                "action_sample": (payload.get("actions") or [None])[0],
                "status": status,
            }
        )

    return {
        "actions_decided_count": len(actions_decided),
        "action_type_counts": dict(action_type_counts),
        "decision_proofs": proofs,
        "actions_total": actions_total,
    }


def _state_hash_final(state) -> str:
    data = {"version": state.version, "aggregates": state.aggregates}
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


def _drift_summary(log_path: str) -> Dict[str, Any]:
    store = FileEventStore(log_path)
    reducer = Reducer(global_aggregate_id=UNIVERSE_AGG_ID)
    register_handlers(reducer)
    replay_result = replay(store, reducer)
    state = replay_result.state

    agents = list_agents(state, UNIVERSE_AGG_ID)
    drift = {}
    for agent_id in agents:
        d = get_drift(state, agent_id, UNIVERSE_AGG_ID)
        drift[agent_id] = {
            "missing_action_ids": d.get("missing_action_ids"),
            "extra_action_ids": d.get("extra_action_ids"),
        }
    drift_count = sum(
        1
        for v in drift.values()
        if v.get("missing_action_ids") or v.get("extra_action_ids")
    )

    agg = state.get_agg(UNIVERSE_AGG_ID)
    u = UniverseState.from_dict(agg if isinstance(agg, dict) else {})
    failure_codes = Counter()
    for f in u.failures:
        code = f.get("error_code") or f.get("result_code") or "UNKNOWN"
        failure_codes[code] += 1

    return {
        "agents": agents,
        "agents_count": len(agents),
        "drift_count": drift_count,
        "drift": drift,
        "failure_codes": dict(failure_codes),
        "state_hash_final": _state_hash_final(state),
    }


def _log_stats(log_path: str) -> Dict[str, Any]:
    total = 0
    first_seq = None
    last_seq = None
    applied_ok = 0
    applied_failed = 0

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            ev = rec.get("event", {})
            seq = ev.get("seq")
            if first_seq is None:
                first_seq = seq
            last_seq = seq
            total += 1
            etype = ev.get("type")
            if etype == "ActionApplied":
                applied_ok += 1
            elif etype == "ActionFailed":
                applied_failed += 1

    return {
        "events_total": total,
        "first_seq": first_seq,
        "last_seq": last_seq,
        "applied_ok": applied_ok,
        "applied_failed": applied_failed,
    }


def _format_markdown(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Audit Report")
    lines.append("")
    lines.append("## Hash Chain")
    lines.append(f"valid: {report['hash_chain']['valid']}")
    lines.append(f"checked: {report['hash_chain']['checked']}")
    if report["hash_chain"].get("error"):
        lines.append(f"error: {report['hash_chain']['error']}")

    lines.append("")
    lines.append("## Decision Ledger Pointers")
    lines.append(f"valid: {report['pointers']['valid']}")
    lines.append(f"checked: {report['pointers']['checked']}")
    if report["pointers"].get("error"):
        lines.append(f"error: {report['pointers']['error']}")

    lines.append("")
    lines.append("## Checkpoint")
    for k, v in report["checkpoint"].items():
        lines.append(f"{k}: {v}")

    lines.append("")
    lines.append("## Decisions")
    lines.append(f"actions_decided_count: {report['decisions']['actions_decided_count']}")
    if report["decisions"]["action_type_counts"]:
        counts = ", ".join(
            f"{k}={v}" for k, v in report["decisions"]["action_type_counts"].items()
        )
        lines.append(f"action_type_counts: {counts}")
    else:
        lines.append("action_type_counts: none")

    lines.append("")
    lines.append("decision_proofs:")
    for i, p in enumerate(report["decisions"]["decision_proofs"], start=1):
        lines.append(
            "proof_{i}: trigger_seq={seq}, trigger_hash={th}, actions_hash={ah}, status={st}".format(
                i=i,
                seq=p.get("trigger_event_seq"),
                th=p.get("trigger_event_hash"),
                ah=p.get("actions_hash"),
                st=p.get("status"),
            )
        )

    lines.append("")
    lines.append("## Drift")
    lines.append(f"drift_count: {report['drift']['drift_count']}")
    if report["drift"]["failure_codes"]:
        codes = ", ".join(
            f"{k}={v}" for k, v in report["drift"]["failure_codes"].items()
        )
        lines.append(f"failure_codes: {codes}")
    else:
        lines.append("failure_codes: none")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate audit report from event log.")
    parser.add_argument("--log", required=True, help="Path to JSONL event log")
    parser.add_argument("--format", default="json", choices=["json", "md", "text"])
    parser.add_argument("--out", help="Output file path")
    parser.add_argument("--checkpoints-dir", help="Directory with checkpoints")
    parser.add_argument("--pubkey", help="Public key PEM for signature verification")
    parser.add_argument("--summary", action="store_true", help="Emit compact summary")
    parser.add_argument("--proof", action="store_true", help="Emit decision proof JSON")
    parser.add_argument("--at-seq", type=int, help="Trigger event seq for proof")
    args = parser.parse_args()

    if args.proof:
        if args.format not in ("json",):
            raise SystemExit("--proof requires --format json")
        proof = build_decision_proof(
            args.log, at_seq=args.at_seq, checkpoints_dir=args.checkpoints_dir, pubkey_path=args.pubkey
        )
        output = json.dumps(proof, sort_keys=True, indent=2)
        if args.out:
            Path(args.out).write_text(output, encoding="utf-8")
        else:
            print(output)
        return 0 if proof.get("valid", False) else 2

    hash_chain = _hash_chain_verify(args.log)
    pointers = verify_actions_decided_pointers(args.log).__dict__
    decisions = _decision_summary(args.log)
    drift = _drift_summary(args.log)
    log_stats = _log_stats(args.log)
    checkpoint = (
        _load_checkpoint_summary(args.checkpoints_dir, args.pubkey)
        if args.checkpoints_dir
        else {"present": False}
    )

    report = {
        "hash_chain": hash_chain,
        "pointers": pointers,
        "checkpoint": checkpoint,
        "decisions": decisions,
        "drift": drift,
        "log": log_stats,
        "state_hash_final": drift.get("state_hash_final"),
        "universe_id": UNIVERSE_AGG_ID,
    }

    if args.summary:
        integrity_ok = bool(hash_chain.get("valid")) and bool(pointers.get("valid"))
        integrity_reason = None
        if not integrity_ok:
            integrity_reason = hash_chain.get("error") or pointers.get("error")

        summary = {
            "universe_id": UNIVERSE_AGG_ID,
            "agents_count": drift.get("agents_count"),
            "events_total": log_stats.get("events_total"),
            "actions_total": decisions.get("actions_total"),
            "applied_ok": log_stats.get("applied_ok"),
            "applied_failed": log_stats.get("applied_failed"),
            "first_seq": log_stats.get("first_seq"),
            "last_seq": log_stats.get("last_seq"),
            "state_hash_final": drift.get("state_hash_final"),
            "decision_proofs": len(decisions.get("decision_proofs", [])),
            "integrity": "ok" if integrity_ok else "fail",
            "integrity_reason": integrity_reason,
        }

        if args.format == "text":
            lines = [
                f"universe_id: {summary['universe_id']}",
                f"agents_count: {summary['agents_count']}",
                f"events_total: {summary['events_total']}",
                f"actions_total: {summary['actions_total']}",
                f"applied_ok: {summary['applied_ok']}",
                f"applied_failed: {summary['applied_failed']}",
                f"first_seq: {summary['first_seq']}",
                f"last_seq: {summary['last_seq']}",
                f"state_hash_final: {summary['state_hash_final']}",
                f"decision_proofs: {summary['decision_proofs']}",
                f"integrity: {summary['integrity']}",
            ]
            if summary["integrity_reason"]:
                lines.append(f"integrity_reason: {summary['integrity_reason']}")
            output = "\n".join(lines)
        else:
            output = json.dumps(summary, sort_keys=True, indent=2)
    else:
        if args.format == "md":
            output = _format_markdown(report)
        else:
            output = json.dumps(report, sort_keys=True, indent=2)

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
