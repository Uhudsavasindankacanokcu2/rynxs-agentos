"""
Verify ActionsDecided pointers against hash-chain.
"""

import json
from dataclasses import dataclass
from typing import Optional

from ..core.events import Event
from ..log.integrity import hash_event, ZERO_HASH


@dataclass
class PointerVerificationResult:
    valid: bool
    checked: int = 0
    error: Optional[str] = None
    mismatch_seq: Optional[int] = None
    expected: Optional[str] = None
    actual: Optional[str] = None


def verify_actions_decided_pointers(log_path: str) -> PointerVerificationResult:
    """
    Verify ActionsDecided trigger pointers against hash-chain.

    Checks:
    - hash chain integrity for each record (prev_hash + event -> event_hash)
    - trigger_event_hash matches hash at trigger_seq
    - trigger_event_type matches event at trigger_seq
    - trigger_spec_hash (if present) matches event payload spec_hash
    """
    seq_to_hash = {}
    seq_to_event = {}

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
                hash_version=ev.get("hash_version"),
            )

            computed_hash = hash_event(prev_hash, event_obj)
            if rec.get("prev_hash") != prev_hash:
                return PointerVerificationResult(
                    valid=False,
                    checked=checked,
                    error="prev_hash mismatch",
                    mismatch_seq=event_obj.seq,
                    expected=prev_hash,
                    actual=rec.get("prev_hash"),
                )
            if rec.get("event_hash") != computed_hash:
                return PointerVerificationResult(
                    valid=False,
                    checked=checked,
                    error="event_hash mismatch",
                    mismatch_seq=event_obj.seq,
                    expected=computed_hash,
                    actual=rec.get("event_hash"),
                )

            seq_to_hash[event_obj.seq] = rec.get("event_hash")
            seq_to_event[event_obj.seq] = ev
            prev_hash = rec.get("event_hash")

            if event_obj.type != "ActionsDecided":
                continue

            payload = ev.get("payload", {}) or {}
            trigger_seq = payload.get("trigger_event_seq")
            trigger_hash = payload.get("trigger_event_hash")
            trigger_type = payload.get("trigger_event_type")
            trigger_spec_hash = payload.get("trigger_spec_hash")

            if trigger_seq is None:
                return PointerVerificationResult(
                    valid=False,
                    checked=checked,
                    error="missing trigger_event_seq",
                    mismatch_seq=event_obj.seq,
                )

            expected_hash = seq_to_hash.get(trigger_seq)
            expected_event = seq_to_event.get(trigger_seq)
            if expected_hash is None or expected_event is None:
                return PointerVerificationResult(
                    valid=False,
                    checked=checked,
                    error="trigger_seq not found",
                    mismatch_seq=event_obj.seq,
                    expected=str(trigger_seq),
                )

            if trigger_hash != expected_hash:
                return PointerVerificationResult(
                    valid=False,
                    checked=checked,
                    error="trigger_event_hash mismatch",
                    mismatch_seq=event_obj.seq,
                    expected=expected_hash,
                    actual=trigger_hash,
                )

            if trigger_type != expected_event.get("type"):
                return PointerVerificationResult(
                    valid=False,
                    checked=checked,
                    error="trigger_event_type mismatch",
                    mismatch_seq=event_obj.seq,
                    expected=expected_event.get("type"),
                    actual=trigger_type,
                )

            if trigger_spec_hash is not None:
                expected_spec_hash = expected_event.get("payload", {}).get("spec_hash")
                if trigger_spec_hash != expected_spec_hash:
                    return PointerVerificationResult(
                        valid=False,
                        checked=checked,
                        error="trigger_spec_hash mismatch",
                        mismatch_seq=event_obj.seq,
                        expected=expected_spec_hash,
                        actual=trigger_spec_hash,
                    )

            checked += 1

    return PointerVerificationResult(valid=True, checked=checked)
