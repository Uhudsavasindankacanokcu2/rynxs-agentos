# CLI (Deterministic Toolchain)

## Purpose
These CLI tools provide deterministic inspection, verification, and audit reporting
for the event-sourced control plane. They are intended for reproducibility,
compliance proof, and operational drift analysis.

## Recommended Usage (Official)
Use the wrapper to ensure clean output and stable environment:

```bash
scripts/engine_cli.sh <command> [args...]
```

## Direct Usage (Advanced)
You can call the module directly, but macOS CLT may emit a cache warning:

```bash
python -m engine.cli.inspect --log /path/to/operator-events.log
```

If you see `xcrun_db` cache warnings, prefer the wrapper above.

## Commands

### inspect
Inspect state and drift for an agent or list all agents.

```bash
scripts/engine_cli.sh inspect --log /path/to/operator-events.log
scripts/engine_cli.sh inspect --log /path/to/operator-events.log --agent universe/agent-001
scripts/engine_cli.sh inspect --log /path/to/operator-events.log --agent agent-001 --at-seq 120
```

### audit_report
Generate an audit report (JSON or Markdown).

```bash
scripts/engine_cli.sh audit_report --log /path/to/operator-events.log --format json
scripts/engine_cli.sh audit_report --log /path/to/operator-events.log --format md --out /tmp/report.md
```

Optional checkpoint verification:

```bash
scripts/engine_cli.sh audit_report \
  --log /path/to/operator-events.log \
  --checkpoints-dir /path/to/checkpoints \
  --pubkey /path/to/public.pem
```

Summary mode (compact):

```bash
scripts/engine_cli.sh audit_report --log /path/to/operator-events.log --summary --format json
scripts/engine_cli.sh audit_report --log /path/to/operator-events.log --summary --format text
```

Proof export:

```bash
scripts/engine_cli.sh audit_report --log /path/to/operator-events.log --proof --format json --out /tmp/proof.json
scripts/engine_cli.sh audit_report --log /path/to/operator-events.log --proof --at-seq 0 --format json --out /tmp/proof-0.json
```

### verify_pointers
Verify ActionsDecided pointers against hash-chain.

```bash
scripts/engine_cli.sh verify_pointers --log /path/to/operator-events.log
```

## Decision Proof (Minimal)

Below is a minimal proof chain extracted from the small fixture log:

```json
{
  "trigger_event": {
    "seq": 0,
    "hash": "9cc66c44bd92206c343d41160092104dfda71582f36006ee1865e95052e8fc3b",
    "type": "AgentObserved",
    "spec_hash": "78fc19249e2d835a"
  },
  "actions_hash": "b5df8601f452c39a7f1e66d979d53ff0ef61b5f7b7501290a586662fe4f5792c",
  "action_ids": [
    "02e2a276c672424e1aa0f575fff03cc35568b37dd0c38021e3d415608ba44f79",
    "698c64c870c510a1a285b989bc3010f209155c14c20b97f10a7c0ebae7037a33"
  ],
  "action_sample": {
    "action_type": "EnsureConfigMap",
    "target": "universe/agent-000-spec",
    "params": {
      "name": "agent-000-spec",
      "namespace": "universe",
      "data": {
        "agent.json": "{\"image\":{\"repository\":\"ghcr.io/test/agent\",\"tag\":\"v1.0.0\",\"verify\":false},\"permissions\":{\"canAccessAuditLogs\":false,\"canAssignTasks\":false,\"canManageTeam\":false},\"role\":\"worker\",\"team\":\"backend-team\",\"workspace\":{\"size\":\"1Gi\"}}"
      }
    }
  },
  "state_hash_final": "6a2d25ae69313ebf7eaa4ce0ef9658b4a6aee6165e2a15edd6b0b6e20b4a4b29"
}
```

This snippet shows:
- The exact trigger event (seq/hash/type/spec_hash)
- The decision hash (actions_hash)
- Concrete action identifiers and a canonical action example
- The final replayed state hash (audit_report summary)

## Examples

### Fixture log
```bash
scripts/engine_cli.sh inspect --log engine/tests/fixtures/operator_log_small.jsonl
scripts/engine_cli.sh audit_report --log engine/tests/fixtures/operator_log_small.jsonl --format md
```

### Real operator log
```bash
scripts/engine_cli.sh inspect --log /var/log/rynxs/operator-events.log
scripts/engine_cli.sh audit_report --log /var/log/rynxs/operator-events.log --format json
```

## Exit Codes
- `0`: success
- `2`: verification failed (e.g., pointer mismatch)
- non-zero: runtime error

## Determinism Gate
The determinism gate runs core tests and basic CLI checks.

```bash
scripts/determinism_gate.sh
```

It executes:
- Determinism/replay tests
- Pointer verification
- Audit report generation
