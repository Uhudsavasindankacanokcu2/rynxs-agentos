# Deterministic Execution Engine

Event-sourced, deterministic execution engine for replayable, verifiable, audit-ready AI workloads.

## Core Principles

1. **Event Sourcing**: All state changes recorded as immutable events (append-only log)
2. **Deterministic Reducers**: Pure functions `(State, Event) -> State` (no side effects, no randomness)
3. **Hash Chain Integrity**: Tamper-evident logging with cryptographic hash chains
4. **Replayability**: Same events always produce same state (100% determinism guarantee)
5. **Checkpoints**: Signed state snapshots for fast replay and audit trails

## Architecture

```
/engine
  /core       # Event, State, Reducer, Clock, IDs
  /log        # EventStore, file_store, integrity verification
  /checkpoint # Checkpoint creation, signing, verification
  /replay     # Replay runner, trace, diff utilities
  /cli        # Command-line interface
  /tests      # Unit tests
```

## Milestones

- **M1**: Deterministic core (Event + State + Reducer)
- **M2**: Append-only EventStore with file backend
- **M3**: Hash-chain integrity (tamper-evident logging)
- **M4**: Checkpoint system (signed snapshots)
- **M5**: Replay system (trace + diff)

See [docs/MILESTONES.md](../docs/MILESTONES.md) for detailed implementation plan.

## Quick Start

```bash
# Initialize event log
engine init --log-path ./logs/universe.log

# Append event
engine append --type AgentCreated --aggregate-id agent-1 --payload '{"name":"alpha"}'

# Verify integrity
engine verify --log-path ./logs/universe.log

# Create checkpoint
engine checkpoint create --at-seq 1000 --key-path ./keys/operator.key

# Replay events
engine replay --log-path ./logs/universe.log --trace
```

## Why This Matters

Current AI systems are black boxes. This engine provides:

- **Auditability**: Every decision recorded and verifiable
- **Reproducibility**: Replay any historical state
- **Accountability**: Cryptographically signed checkpoints
- **Trust**: Tamper-evident logs (hash chains)

This is the foundation for governable AI infrastructure.
