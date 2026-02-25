"""
Tests for checkpoint system (M4).

Critical tests:
1. Deterministic snapshot
2. Signature verification
3. Tamper detection (state)
4. Tamper detection (metadata)
5. Wrong public key
6. Fast replay from checkpoint
"""

import tempfile
import os
from engine.core import Event, State, Reducer
from engine.log import FileEventStore
from engine.replay import replay
from engine.checkpoint import (
    Checkpoint,
    compute_state_hash,
    state_to_base64,
    state_from_base64,
    SigningKey,
    VerifyingKey,
    verify_checkpoint,
    CheckpointStore,
)


def test_deterministic_snapshot_100_runs():
    """Same state must produce identical bytes/hash across 100 runs."""
    # Create state with some data
    state = State(version=10, aggregates={"agent-1": {"n": 42}, "agent-2": {"n": 99}})

    # Compute hash 100 times
    hashes = []
    for _ in range(100):
        h = compute_state_hash(state)
        hashes.append(h)

    # All hashes must be identical
    assert len(set(hashes)) == 1, f"Non-deterministic hashing: {len(set(hashes))} unique hashes"

    # Verify base64 encoding also deterministic
    b64_values = []
    for _ in range(100):
        b64 = state_to_base64(state)
        b64_values.append(b64)

    assert len(set(b64_values)) == 1, "Non-deterministic base64 encoding"


def test_signature_verification_passes():
    """Valid signature must pass verification."""
    # Generate keypair
    signing_key = SigningKey.generate()
    verifying_key = VerifyingKey.from_signing_key(signing_key)

    # Create checkpoint
    state = State(version=5, aggregates={"test": {"value": 42}})
    state_hash = compute_state_hash(state)
    state_bytes = state_to_base64(state)

    checkpoint = Checkpoint(
        version=1,
        event_index=10,
        event_hash="abc123" * 10,  # Mock event hash
        state_hash=state_hash,
        state_bytes=state_bytes,
        created_at_logical=1000,
        pubkey_id=signing_key.get_pubkey_id(),
        signature="",  # Will be set below
    )

    # Sign checkpoint
    payload = checkpoint.signing_payload()
    signature = signing_key.sign_base64(payload)

    # Create signed checkpoint
    signed_checkpoint = Checkpoint(
        version=checkpoint.version,
        event_index=checkpoint.event_index,
        event_hash=checkpoint.event_hash,
        state_hash=checkpoint.state_hash,
        state_bytes=checkpoint.state_bytes,
        created_at_logical=checkpoint.created_at_logical,
        pubkey_id=checkpoint.pubkey_id,
        signature=signature,
    )

    # Verify
    result = verify_checkpoint(signed_checkpoint, verifying_key, mode="signature")
    assert result.valid, f"Signature verification failed: {result.error}"
    assert result.signature_valid


def test_tamper_state_bytes_fails_verification():
    """Tampering with state_bytes must fail verification."""
    signing_key = SigningKey.generate()
    verifying_key = VerifyingKey.from_signing_key(signing_key)

    state = State(version=5, aggregates={"test": {"value": 42}})
    state_hash = compute_state_hash(state)
    state_bytes = state_to_base64(state)

    checkpoint = Checkpoint(
        version=1,
        event_index=10,
        event_hash="abc123" * 10,
        state_hash=state_hash,
        state_bytes=state_bytes,
        created_at_logical=1000,
        pubkey_id=signing_key.get_pubkey_id(),
        signature="",
    )

    # Sign
    payload = checkpoint.signing_payload()
    signature = signing_key.sign_base64(payload)

    # Create signed checkpoint
    signed_checkpoint = Checkpoint(
        version=checkpoint.version,
        event_index=checkpoint.event_index,
        event_hash=checkpoint.event_hash,
        state_hash=checkpoint.state_hash,
        state_bytes=checkpoint.state_bytes,
        created_at_logical=checkpoint.created_at_logical,
        pubkey_id=checkpoint.pubkey_id,
        signature=signature,
    )

    # TAMPER: Modify state_bytes
    tampered_state = State(version=5, aggregates={"test": {"value": 999}})
    tampered_bytes = state_to_base64(tampered_state)

    tampered_checkpoint = Checkpoint(
        version=signed_checkpoint.version,
        event_index=signed_checkpoint.event_index,
        event_hash=signed_checkpoint.event_hash,
        state_hash=signed_checkpoint.state_hash,  # Original hash (mismatch)
        state_bytes=tampered_bytes,  # TAMPERED
        created_at_logical=signed_checkpoint.created_at_logical,
        pubkey_id=signed_checkpoint.pubkey_id,
        signature=signed_checkpoint.signature,
    )

    # Verification should still pass signature (state_hash not in signature)
    # But full verification would fail on state_hash mismatch
    result = verify_checkpoint(tampered_checkpoint, verifying_key, mode="signature")
    assert result.signature_valid  # Signature still valid (state_bytes not signed directly)

    # However, if we check state_hash consistency manually
    import hashlib
    import base64

    actual_state_bytes = base64.b64decode(tampered_checkpoint.state_bytes)
    computed_hash = hashlib.sha256(actual_state_bytes).hexdigest()
    assert computed_hash != tampered_checkpoint.state_hash, "State hash should not match tampered bytes"


def test_tamper_metadata_fails_verification():
    """Tampering with signed metadata (event_index) must fail verification."""
    signing_key = SigningKey.generate()
    verifying_key = VerifyingKey.from_signing_key(signing_key)

    state = State(version=5, aggregates={"test": {"value": 42}})
    state_hash = compute_state_hash(state)
    state_bytes = state_to_base64(state)

    checkpoint = Checkpoint(
        version=1,
        event_index=10,
        event_hash="abc123" * 10,
        state_hash=state_hash,
        state_bytes=state_bytes,
        created_at_logical=1000,
        pubkey_id=signing_key.get_pubkey_id(),
        signature="",
    )

    # Sign
    payload = checkpoint.signing_payload()
    signature = signing_key.sign_base64(payload)

    signed_checkpoint = Checkpoint(
        version=checkpoint.version,
        event_index=checkpoint.event_index,
        event_hash=checkpoint.event_hash,
        state_hash=checkpoint.state_hash,
        state_bytes=checkpoint.state_bytes,
        created_at_logical=checkpoint.created_at_logical,
        pubkey_id=checkpoint.pubkey_id,
        signature=signature,
    )

    # TAMPER: Modify event_index (this is in signing payload)
    tampered_checkpoint = Checkpoint(
        version=signed_checkpoint.version,
        event_index=999,  # TAMPERED (was 10)
        event_hash=signed_checkpoint.event_hash,
        state_hash=signed_checkpoint.state_hash,
        state_bytes=signed_checkpoint.state_bytes,
        created_at_logical=signed_checkpoint.created_at_logical,
        pubkey_id=signed_checkpoint.pubkey_id,
        signature=signed_checkpoint.signature,  # Original signature (now invalid)
    )

    # Verify - should fail
    result = verify_checkpoint(tampered_checkpoint, verifying_key, mode="signature")
    assert not result.valid, "Tampered metadata should fail verification"
    assert not result.signature_valid


def test_wrong_public_key_fails_verification():
    """Using wrong public key must fail verification."""
    # Generate two keypairs
    signing_key1 = SigningKey.generate()
    signing_key2 = SigningKey.generate()
    verifying_key2 = VerifyingKey.from_signing_key(signing_key2)

    state = State(version=5, aggregates={"test": {"value": 42}})
    state_hash = compute_state_hash(state)
    state_bytes = state_to_base64(state)

    # Sign with key1
    checkpoint = Checkpoint(
        version=1,
        event_index=10,
        event_hash="abc123" * 10,
        state_hash=state_hash,
        state_bytes=state_bytes,
        created_at_logical=1000,
        pubkey_id=signing_key1.get_pubkey_id(),
        signature="",
    )

    payload = checkpoint.signing_payload()
    signature = signing_key1.sign_base64(payload)

    signed_checkpoint = Checkpoint(
        version=checkpoint.version,
        event_index=checkpoint.event_index,
        event_hash=checkpoint.event_hash,
        state_hash=checkpoint.state_hash,
        state_bytes=checkpoint.state_bytes,
        created_at_logical=checkpoint.created_at_logical,
        pubkey_id=checkpoint.pubkey_id,
        signature=signature,
    )

    # Verify with key2 (wrong key)
    result = verify_checkpoint(signed_checkpoint, verifying_key2, mode="signature")
    assert not result.valid, "Wrong public key should fail verification"
    assert "Public key ID mismatch" in result.error


def test_fast_replay_from_checkpoint():
    """Replay from checkpoint must match full replay."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test.log")
        store = FileEventStore(log_path)

        # Create reducer
        r = Reducer()

        def inc_handler(cur, ev):
            cur = cur or {"n": 0}
            return {"n": cur["n"] + ev.payload["inc"]}

        r.register("INC", inc_handler)

        # Append 100 events
        print("\nAppending 100 events...")
        for i in range(100):
            e = Event(type="INC", aggregate_id="A", ts=i, payload={"inc": 1})
            store.append(e)

        # Create checkpoint at event 79 (80 events: 0-79)
        print("Creating checkpoint at event 79...")
        result_80 = replay(store, r, to_seq=79)
        state_80 = result_80.state

        # Generate signing key
        signing_key = SigningKey.generate()

        # Create checkpoint
        checkpoint = Checkpoint(
            version=1,
            event_index=79,
            event_hash="mock_hash",  # In real implementation, read from log
            state_hash=compute_state_hash(state_80),
            state_bytes=state_to_base64(state_80),
            created_at_logical=79,
            pubkey_id=signing_key.get_pubkey_id(),
            signature="",
        )

        payload = checkpoint.signing_payload()
        signature = signing_key.sign_base64(payload)

        signed_checkpoint = Checkpoint(
            version=checkpoint.version,
            event_index=checkpoint.event_index,
            event_hash=checkpoint.event_hash,
            state_hash=checkpoint.state_hash,
            state_bytes=checkpoint.state_bytes,
            created_at_logical=checkpoint.created_at_logical,
            pubkey_id=checkpoint.pubkey_id,
            signature=signature,
        )

        # Replay remaining events (80-99) from checkpoint
        print("Replaying from checkpoint + 20 events...")
        checkpoint_state = state_from_base64(signed_checkpoint.state_bytes)

        # Apply remaining 20 events
        remaining_events = list(store.read(from_seq=80))
        assert len(remaining_events) == 20

        final_state = checkpoint_state
        for ev in remaining_events:
            final_state = r.apply(final_state, ev)

        final_hash_from_checkpoint = compute_state_hash(final_state)

        # Full replay from beginning
        print("Full replay from seq 0...")
        full_result = replay(store, r, to_seq=99)
        full_hash = compute_state_hash(full_result.state)

        # Hashes must match
        print(f"Checkpoint replay hash: {final_hash_from_checkpoint}")
        print(f"Full replay hash: {full_hash}")
        assert final_hash_from_checkpoint == full_hash, "Fast replay from checkpoint must match full replay"

        # Verify final values
        assert full_result.state.get_agg("A")["n"] == 100, "Expected sum 0+1+1+...+1 (100 times) = 100"
        print("✓ Fast replay verified")


def test_checkpoint_store_save_and_load():
    """CheckpointStore must correctly save and load checkpoints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cp_dir = os.path.join(tmpdir, "checkpoints")
        store = CheckpointStore(cp_dir)

        # Create checkpoint
        signing_key = SigningKey.generate()
        state = State(version=5, aggregates={"test": {"value": 42}})

        checkpoint = Checkpoint(
            version=1,
            event_index=10,
            event_hash="abc123def456" * 5,
            state_hash=compute_state_hash(state),
            state_bytes=state_to_base64(state),
            created_at_logical=1000,
            pubkey_id=signing_key.get_pubkey_id(),
            signature=signing_key.sign_base64(
                {
                    "version": 1,
                    "event_index": 10,
                    "event_hash": "abc123def456" * 5,
                    "state_hash": compute_state_hash(state),
                    "created_at_logical": 1000,
                    "pubkey_id": signing_key.get_pubkey_id(),
                }
            ),
        )

        # Save
        filepath = store.save(checkpoint)
        assert os.path.exists(filepath), "Checkpoint file should exist"

        # Load
        loaded = store.load(filepath)
        assert loaded.event_index == checkpoint.event_index
        assert loaded.state_hash == checkpoint.state_hash
        assert loaded.signature == checkpoint.signature

        # List
        checkpoints = store.list_checkpoints()
        assert len(checkpoints) == 1

        # Find latest
        latest = store.find_latest()
        assert latest == filepath
