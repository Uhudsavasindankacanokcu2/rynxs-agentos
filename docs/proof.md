# Proof Scenario (Deterministic "Ispat")

This document defines the deterministic scenario used to prove that the Universe Model correctly enforces its control plane.

## Goal
Demonstrate that the system enforces:
- **Social Sharding**: Relationship changes lead to predictable zone weights.
- **Physics Drift**: Zonal physics drift leads to predictable effective jitter.
- **Health-based Lifecycle**: Fragmentation thresholds trigger deterministic sleep cycles.
- **3-Tier Memory Invariants**:
    - RAM: Volatile, resets after death.
    - Volume: Persistent, survives deaths.
    - Bucket: Immutable atomic snapshots.

## Deterministic Run Configuration
To achieve reproducibility, the following environment variables/config must be set:
- `RANDOM_SEED=42`
- `JITTER_SEED=42`
- `LUCK_SEED=42`
- `DRIFT_TICK_SECONDS=60`
- Fixed `config/relationships.json`.

## Scenario Steps
1. **Birth**: Start agent, verify `BIRTH` event and `ATTACHED` binding status.
2. **Growth**: Process N messages to increase RAM state.
3. **Drift**: Observe `STATE_DRIFT` logs every minute.
4. **Light Sleep (T1)**: Force `Frag > T1` via RAM growth -> Verify volume.json update.
5. **Deep Sleep (T2)**: Force `Frag > T2` via time/stress -> Verify bucket snapshot creation.
6. **Death and Resurrection**: Send SIGKILL -> Restart -> Verify:
    - ram.json is fresh.
    - volume.json is restored.
    - audit.jsonl shows `RESPAWN` from `VOLUME`.

## Success Invariants
- **RAM**: /workspace/state/ram.json resets after `DEATH`.
- **Volume**: /workspace/state/volume.json persists across runs.
- **Bucket**: Snapshots are immutable and content-addressed.
