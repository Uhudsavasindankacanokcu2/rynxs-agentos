# M4: Checkpoint System

## Goal

Implement signed state snapshots for fast replay and audit trails. Checkpoints capture the state at a specific sequence number, along with cryptographic signatures to prove authenticity.

## Description

Create checkpoint system:
- **Checkpoint**: Snapshot of state at specific seq, with hashes and signature
- **Signer**: Sign checkpoints using Ed25519 keypair
- **Verifier**: Verify checkpoint signatures and validate hashes match replay
- **Snapshot**: Create checkpoint from replayed state + log hash

Checkpoints enable:
- Fast replay (start from checkpoint instead of seq 0)
- Audit trails (signed proof of state at specific point in time)
- Tamper detection (verify state_hash matches replay)

## Files to Create

- `engine/checkpoint/__init__.py`
- `engine/checkpoint/model.py` - Checkpoint dataclass
- `engine/checkpoint/signer.py` - Sign checkpoints with Ed25519
- `engine/checkpoint/verify.py` - Verify checkpoint signatures and hashes
- `engine/checkpoint/snapshot.py` - Create checkpoint from state
- `engine/tests/test_checkpoint.py` - Checkpoint creation and verification tests

## Acceptance Criteria

- [ ] Checkpoint model includes: checkpoint_id, at_seq, state_hash, log_hash, signature, timestamp, created_by
- [ ] state_hash: SHA-256 of canonical JSON state
- [ ] log_hash: hash of event at at_seq (from hash chain)
- [ ] Signature: Ed25519 signature of (checkpoint_id + at_seq + state_hash + log_hash)
- [ ] Signer generates Ed25519 keypair (or loads from file)
- [ ] Verifier checks: signature valid, public key matches, hashes match
- [ ] Snapshot utility: replay to at_seq, compute state_hash, create checkpoint
- [ ] Checkpoints stored as JSON files with .checkpoint extension
- [ ] Tests verify: create checkpoint, replay to same seq, verify state_hash matches
- [ ] Tests verify: tampered checkpoint (modified state_hash) fails verification

## Test Requirements

Create `test_checkpoint.py` with tests for:

1. **Create and Verify**: Create checkpoint at seq 100, verify signature and hashes
2. **Replay Verification**: Replay to seq 100, create checkpoint, compare state_hash with original
3. **Tamper Detection - State Hash**: Modify state_hash in checkpoint, verify fails
4. **Tamper Detection - Log Hash**: Modify log_hash, verify fails
5. **Tamper Detection - Signature**: Modify signature, verify fails
6. **Key Management**: Generate keypair, save to file, load from file, verify works
7. **Fast Replay**: Replay from checkpoint (not seq 0), verify performance improvement

```python
def test_checkpoint_creation_and_verification():
    """Create checkpoint and verify signature + hashes."""
    # Create log with 100 events
    store = FileStore(path="./test.log")
    for i in range(100):
        store.append(create_test_event(seq=i))

    # Replay to seq 99 (100 events: 0-99)
    events = store.read_all()
    state = replay(events)

    # Create checkpoint
    keypair = generate_keypair()
    checkpoint = create_checkpoint(
        at_seq=99,
        state=state,
        log_hash=compute_event_hash(events[99]),
        keypair=keypair,
        created_by="operator"
    )

    # Verify checkpoint
    result = verify_checkpoint(checkpoint, keypair.public_key, store)
    assert result.valid == True
    assert result.state_matches == True
    assert result.signature_valid == True
```

## Implementation Notes

**Checkpoint Model**:
```python
from dataclasses import dataclass
from typing import Any

@dataclass
class Checkpoint:
    checkpoint_id: str         # e.g., "checkpoint-1000-20260225T120000"
    at_seq: int                # Sequence number where checkpoint was taken
    state_hash: str            # SHA-256 of canonical JSON state
    log_hash: str              # Hash of event at at_seq (from hash chain)
    signature: str             # Ed25519 signature (hex string)
    timestamp: int             # When checkpoint was created (monotonic)
    created_by: str            # e.g., "operator", "admin"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return self.__dict__

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Checkpoint':
        """Deserialize from dict."""
        return cls(**data)
```

**Signer**:
```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
import hashlib

@dataclass
class Keypair:
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey

    def sign(self, message: bytes) -> bytes:
        """Sign message with private key."""
        return self.private_key.sign(message)

    def verify(self, signature: bytes, message: bytes) -> bool:
        """Verify signature with public key."""
        try:
            self.public_key.verify(signature, message)
            return True
        except:
            return False

def generate_keypair() -> Keypair:
    """Generate new Ed25519 keypair."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return Keypair(private_key=private_key, public_key=public_key)

def save_keypair(keypair: Keypair, private_path: str, public_path: str):
    """Save keypair to PEM files."""
    # Save private key
    private_pem = keypair.private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    with open(private_path, 'wb') as f:
        f.write(private_pem)

    # Save public key
    public_pem = keypair.public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open(public_path, 'wb') as f:
        f.write(public_pem)

def load_keypair(private_path: str, public_path: str) -> Keypair:
    """Load keypair from PEM files."""
    with open(private_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    with open(public_path, 'rb') as f:
        public_key = serialization.load_pem_public_key(f.read())

    return Keypair(private_key=private_key, public_key=public_key)

def create_checkpoint(at_seq: int, state: State, log_hash: str, keypair: Keypair, created_by: str) -> Checkpoint:
    """Create signed checkpoint."""
    # Compute state hash
    state_hash = compute_state_hash(state)

    # Generate checkpoint ID
    from datetime import datetime
    timestamp = int(datetime.utcnow().timestamp())
    checkpoint_id = f"checkpoint-{at_seq}-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}"

    # Create signature message: checkpoint_id + at_seq + state_hash + log_hash
    message = f"{checkpoint_id}|{at_seq}|{state_hash}|{log_hash}".encode('utf-8')
    signature_bytes = keypair.sign(message)
    signature = signature_bytes.hex()

    return Checkpoint(
        checkpoint_id=checkpoint_id,
        at_seq=at_seq,
        state_hash=state_hash,
        log_hash=log_hash,
        signature=signature,
        timestamp=timestamp,
        created_by=created_by
    )

def compute_state_hash(state: State) -> str:
    """Compute SHA-256 hash of state (canonical JSON)."""
    state_dict = state.__dict__
    canonical = json.dumps(state_dict, sort_keys=True, separators=(',', ':'))
    hash_bytes = hashlib.sha256(canonical.encode('utf-8')).digest()
    return hash_bytes.hex()
```

**Verifier**:
```python
@dataclass
class VerificationResult:
    valid: bool
    signature_valid: bool
    state_matches: bool
    log_matches: bool
    error: str | None = None

def verify_checkpoint(checkpoint: Checkpoint, public_key: Ed25519PublicKey, store: EventStore) -> VerificationResult:
    """
    Verify checkpoint:
    1. Signature is valid
    2. state_hash matches replay to at_seq
    3. log_hash matches event at at_seq
    """
    # Verify signature
    message = f"{checkpoint.checkpoint_id}|{checkpoint.at_seq}|{checkpoint.state_hash}|{checkpoint.log_hash}".encode('utf-8')
    signature_bytes = bytes.fromhex(checkpoint.signature)

    try:
        public_key.verify(signature_bytes, message)
        signature_valid = True
    except:
        return VerificationResult(
            valid=False,
            signature_valid=False,
            state_matches=False,
            log_matches=False,
            error="Invalid signature"
        )

    # Replay to at_seq and verify state_hash
    events = store.get_since_seq(0)
    replay_events = [e for e in events if e.seq <= checkpoint.at_seq]
    replayed_state = replay(replay_events)
    replayed_state_hash = compute_state_hash(replayed_state)

    state_matches = (replayed_state_hash == checkpoint.state_hash)

    # Verify log_hash
    event_at_seq = [e for e in events if e.seq == checkpoint.at_seq][0]
    actual_log_hash = compute_event_hash(event_at_seq)
    log_matches = (actual_log_hash == checkpoint.log_hash)

    valid = signature_valid and state_matches and log_matches

    return VerificationResult(
        valid=valid,
        signature_valid=signature_valid,
        state_matches=state_matches,
        log_matches=log_matches,
        error=None if valid else "Checkpoint verification failed"
    )
```

## CLI Commands

```bash
# Generate keypair
engine keygen --private-key ./keys/operator.key --public-key ./keys/operator.pub

# Create checkpoint at specific sequence
engine checkpoint create \
  --log-path ./logs/universe.log \
  --at-seq 1000 \
  --key-path ./keys/operator.key \
  --output ./checkpoints/ \
  --created-by operator

# Output: checkpoints/checkpoint-1000-20260225T120000.checkpoint

# Verify checkpoint
engine checkpoint verify \
  --checkpoint-path ./checkpoints/checkpoint-1000-20260225T120000.checkpoint \
  --log-path ./logs/universe.log \
  --public-key ./keys/operator.pub

# Output:
# Checkpoint ID: checkpoint-1000-20260225T120000
# At sequence: 1000
# State hash: abc123...
# Log hash: def456...
# Signature: VALID (Ed25519)
#
# Replaying to seq 1000 to verify state_hash...
# Replayed state hash: abc123... (MATCH)
# Event log hash at seq 1000: def456... (MATCH)
#
# Checkpoint verification: PASSED
```

## Definition of Done

- Checkpoint model implemented with all required fields
- Ed25519 signer and verifier implemented
- Checkpoint creation creates valid signatures
- Verification checks signatures, state_hash, and log_hash
- All tests pass (creation, verification, tamper detection)
- CLI commands implemented (keygen, checkpoint create, checkpoint verify)
- Documentation includes examples of checkpoint workflow

## Labels

`milestone:M4` `priority:high` `type:security` `deterministic-engine`
