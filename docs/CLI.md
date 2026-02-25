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

### verify_pointers
Verify ActionsDecided pointers against hash-chain.

```bash
scripts/engine_cli.sh verify_pointers --log /path/to/operator-events.log
```

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
