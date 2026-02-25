# Hash Versioning (Event Commitment Surface)

## Why Versioning?
We need to evolve the canonical event payload without breaking replay/audit guarantees.
Versioning allows us to change hashing rules while still verifying older logs.

## v1 (Current / Backward Compatible)
- `meta` is always included in the canonical hash payload.
- Empty `meta` hashes as `{}`.
- No `hash_version` field is present.

## v2 (Optional, Clean Surface)
- `hash_version: "v2"` is included in the canonical hash payload.
- `meta` is **omitted** from the hash payload if empty.
- `meta` is included only when non-empty.

## Enable v2
Set:
```
RYNXS_HASH_VERSION=v2
```

This is applied at append time by the EventStore.

## Migration Plan
1. **Staging first**: enable `RYNXS_HASH_VERSION=v2` and validate determinism gate.
2. **Regenerate fixtures** (only if you choose to migrate fixtures to v2):
   - Rebuild golden logs with `RYNXS_HASH_VERSION=v2`.
   - Update expected state hashes.
3. **Production rollout**:
   - Enable v2 in operator env.
   - Keep old logs (v1) readable; replay/verify still works.

## Compatibility
- v1 logs remain verifiable because v1 hash rules are preserved.
- v2 logs are self-describing via `hash_version`.
- Mixed logs are supported: events without `hash_version` use v1 rules.
