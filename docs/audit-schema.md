# Audit Event Schema

This document defines the unified schema for audit events recorded in /workspace/audit.jsonl.

## Common Fields
All events contain the following baseline:
- `t`: Timestamp (Unix seconds).
- `event`: Event identifier (string).
- `agent`: Agent name.
- `ns`: Kubernetes namespace.
- `consciousness_id`: Identity identifier.
- `run_id`: Run instance identifier.

## Event Types

### BIRTH
Fired when the agent runtime initializes.
- `binding_status`: ATTACHED / DETACHED.
- `zone_weights`: Initial social shard distribution.
- `epsilon_entity`: Initial physics jitter.

### STATE_DRIFT
Fired during periodic physics/social recalculations.
- `zone_weights`: Updated distribution.
- `epsilon_entity`: Updated physics noise.
- `frag_index`: Health/fragmentation level.
- `stress`: Current stress metric.

### LUCK_APPLIED
Fired when macro luck impacts a decision.
- `macroLuckRate`: Current policy rate (0.01-0.10).
- `luck_hit`: Whether the luck roll succeeded.
- `luck_scope`: Decision area (e.g., event_selection).

### LIGHT_SLEEP
Fired when FragmentationIndex passes T1.
- `trigger`: Threshold reason.
- `ram_to_volume_written`: Boolean.

### DEEP_SLEEP
Fired when FragmentationIndex passes T2.
- `snapshot_path`: Path to the atomic bucket snapshot.
- `sha256`: SHA256 hash of the snapshot content.

### DEATH
Fired on graceful shutdown or fatal error.
- `reason`: Shutdown trigger.
- `ram_wiped`: Boolean.

### RESPAWN
- `restored_from`: `VOLUME | BUCKET | NONE`
- `restore_ok`: Boolean.
