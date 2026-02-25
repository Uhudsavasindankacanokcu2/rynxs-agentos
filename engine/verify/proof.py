"""
Decision proof builder and verifier.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .pointers import verify_actions_decided_pointers


@dataclass
class ProofVerificationResult:
    valid: bool
    errors: List[str]


def _load_log_records(log_path: str) -> List[Dict[str, Any]]:
    records = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            records.append(json.loads(line))
    return records


def build_decision_proof(
    log_path: str,
    at_seq: Optional[int] = None,
    checkpoints_dir: Optional[str] = None,
    pubkey_path: Optional[str] = None,
) -> Dict[str, Any]:
    records = _load_log_records(log_path)
    seq_to_event = {rec["event"]["seq"]: rec["event"] for rec in records}
    seq_to_hash = {rec["event"]["seq"]: rec["event_hash"] for rec in records}

    decided = None
    for rec in records:
        ev = rec["event"]
        if ev.get("type") != "ActionsDecided":
            continue
        payload = ev.get("payload", {}) or {}
        if at_seq is None or payload.get("trigger_event_seq") == at_seq:
            decided = ev
            break

    if not decided:
        return {
            "valid": False,
            "error": "ActionsDecided not found for given seq",
        }

    payload = decided.get("payload", {}) or {}
    trigger_seq = payload.get("trigger_event_seq")
    trigger_event = seq_to_event.get(trigger_seq, {})
    trigger_hash = seq_to_hash.get(trigger_seq)

    # Collect action results
    all_results = {}
    for rec in records:
        ev = rec["event"]
        if ev.get("type") not in ("ActionApplied", "ActionFailed"):
            continue
        p = ev.get("payload", {}) or {}
        aid = p.get("action_id")
        if not aid:
            continue
        all_results[aid] = {
            "type": ev.get("type"),
            "result_code": p.get("result_code"),
            "resource_ref": p.get("resource_ref"),
            "operation": p.get("operation"),
            "noop": p.get("noop"),
            "status_code": p.get("status_code"),
            "desired_hash": p.get("desired_hash"),
            "observed_hash": p.get("observed_hash"),
            "error": p.get("error"),
        }

    action_ids = payload.get("action_ids", []) or []
    action_results = {}
    for aid in action_ids:
        if aid in all_results:
            action_results[aid] = all_results[aid]
        else:
            action_results[aid] = {"missing": True}

    checkpoint_info = None
    if checkpoints_dir:
        from ..checkpoint.store import CheckpointStore

        store = CheckpointStore(checkpoints_dir)
        cp_path = store.find_at_or_before(trigger_seq)
        if cp_path:
            cp = store.load(cp_path)
            checkpoint_info = {
                "path": cp_path,
                "event_index": cp.event_index,
                "event_hash": cp.event_hash,
                "state_hash": cp.state_hash,
                "pubkey_id": cp.pubkey_id,
                "signature_valid": None,
                "error": None,
            }
            if pubkey_path:
                try:
                    from ..checkpoint.signer import VerifyingKey
                    from ..checkpoint.verify import verify_signature

                    key = VerifyingKey.load_from_file(pubkey_path)
                    result = verify_signature(cp, key)
                    checkpoint_info["signature_valid"] = result.signature_valid
                    checkpoint_info["error"] = result.error
                except Exception as ex:
                    checkpoint_info["signature_valid"] = False
                    checkpoint_info["error"] = str(ex)

    verification = _verify_proof(payload, trigger_event, trigger_hash, action_results, log_path)

    return {
        "valid": verification.valid,
        "verification": {
            "valid": verification.valid,
            "errors": verification.errors,
        },
        "trigger_event": {
            "seq": trigger_seq,
            "hash": trigger_hash,
            "type": trigger_event.get("type"),
            "spec_hash": trigger_event.get("payload", {}).get("spec_hash"),
        },
        "actions_decided": {
            "actions_hash": payload.get("actions_hash"),
            "action_ids": action_ids,
            "actions": payload.get("actions", []),
            "trigger_event_hash": payload.get("trigger_event_hash"),
            "trigger_event_type": payload.get("trigger_event_type"),
            "trigger_spec_hash": payload.get("trigger_spec_hash"),
        },
        "action_results": action_results,
        "checkpoint": checkpoint_info,
    }


def _verify_proof(
    decided_payload: Dict[str, Any],
    trigger_event: Dict[str, Any],
    trigger_hash: Optional[str],
    action_results: Dict[str, Any],
    log_path: str,
) -> ProofVerificationResult:
    errors = []

    pointer_result = verify_actions_decided_pointers(log_path)
    if not pointer_result.valid:
        errors.append(pointer_result.error or "pointer verification failed")

    if decided_payload.get("trigger_event_hash") != trigger_hash:
        errors.append("trigger_event_hash mismatch")
    if decided_payload.get("trigger_event_type") != trigger_event.get("type"):
        errors.append("trigger_event_type mismatch")

    if decided_payload.get("trigger_spec_hash") is not None:
        expected = trigger_event.get("payload", {}).get("spec_hash")
        if decided_payload.get("trigger_spec_hash") != expected:
            errors.append("trigger_spec_hash mismatch")

    for aid in decided_payload.get("action_ids", []):
        if aid not in action_results:
            errors.append(f"missing action_result for {aid}")
            continue
        if action_results[aid].get("missing"):
            errors.append(f"missing action_result for {aid}")

    return ProofVerificationResult(valid=(len(errors) == 0), errors=errors)
