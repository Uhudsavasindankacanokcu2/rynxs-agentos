# Universe Model (v0.1 Spec)

This document defines the core primitives, lifecycle functions, and dynamics of the Universe Model, which governs how AI agents (Entities) exist and interact within the system.

## 1. Core Primitives

### Entities
- **Pod (Body / Entity)**: The lived instance with bounded resources (Kubernetes Pod).
- **Consciousness (Upper being)**: Identity-bearing controller that attaches to a pod.
- **Binding**: API-key or credential-based attachment of consciousness → pod.
- **Control Plane**: The "laws" of the universe, implemented as reconciliation loops (controllers).

### Memory Layers
- **RAM (Volatile)**: Live experience stream; resets on pod death/restart.
- **VOLUME (Personal Persistent)**: Personal memory layer; survives pod death.
- **BUCKET (Snapshots/Archives)**: Atomic checkpoints and deep sleep output.
    - `bucket/pod/*`: Body checkpoint.
    - `bucket/consciousness/*`: Consciousness snapshot.

---

## 2. Lifecycle Functions

Definitions for birth, awake, sleep, death, and respawn sequences.

- **Birth()**: Spawns a new Pod (Entity instance).
- **AwakeLoop()**: Event-driven state updates where RAM grows through experience.
- **LightSleep()**: RAM housekeeping and incremental writes to the Volume.
- **DeepSleep()**: Data compaction and providing an atomic snapshot to the Bucket.
- **Death()**: Detachment of consciousness; RAM is wiped.
- **Respawn()**: A new pod appears; consciousness rebinds and state is restored.

### Restore Rules
- **RAM-only**: Lost forever on death.
- **Volume**: Recoverable across pod respawns.
- **Bucket**: Full state restore possible.

---

## 3. Hybrid Universe Dynamics

The system operates in a dual-mode engine:
- **Event-driven (Day)**: State evolves through continuous event streams.
- **Reconcile/Compaction (Night)**: Deep sleep window where states are consolidated and snapshotted.

---

## 4. Luck & Physics Variability

### MacroLuckPolicy (Story/Opportunity Layer)
- **macroLuckRate**: ∈ [0.01, 0.10] (1%–10%)
- **Impacts**: Event selection bias, encounter routing (who meets whom), and minor reward noise.

### PhysicsJitterPolicy (Micro-physics Layer)
- **physicsJitter**: ∈ [0.00001, 0.0001] (0.001%–0.01%)
- **Zonal by default**: Global jitter is rare (epoch-like events).
- **globalJitterRareEventRate**: Extremely low frequency.
- **Constraint**: Jitter is bounded and limited to slow drift (no sudden jumps).

---

## 5. Zones (Abstract, Social-Graph Sharding)

Zones are not geographic; they are **graph-topological shards** derived from realistic social bonds.

### Relationship Graph Edges
Edges represent various connections (Family, Friends, Work, etc.) with specific attributes:
- **Attributes**: Type, Intensity, Recency, Frequency, Stability, Trust, Obligation.
- **Valence**: ∈ [-1, +1] (Positive vs. Negative).
- **Coupling C(u,v)**: Strength of entanglement (affects zone assignment).

---

## 6. Weighted Multi-Zone Membership

Entities can belong to multiple zones simultaneously (Multi-homing).
- **Weight Calculation**: `pZ = Affinity(u,Z) / Σ Affinity(u,all zones)`.
- **Top K Zones**: Usually limited to K≈3 for realism (e.g., Family, Work, Friends).
- **Effective Physics**: Derived from the weighted average of the member zones' physics.

---

## 7. Sub-Personas

A person maintains their core identity while adapting via weighted sub-personas according to context.
- **α(u) CoreDominance**: Stability of the self.
- **β(u) Flexibility**: Speed of adaptation.
- **γ(u) Separation**: Degree of differentiation between sub-personas.

---

## 8. Sleep Outcomes

Sleep attempts result in one of three outcomes:
- **SUCCESS**: Full restoration.
- **PARTIAL**: Restored but with noticeable "fatigue" or data gaps.
- **FAILED**: Restoration failed; pod remains in a degraded state.

---

## 9. Backup Types

- **Instant Backup**: Rolling mini-checkpoints (summaries/deltas) during awake time.
- **Deep Backup**: Atomic snapshots, compaction, and narrative stitching during Deep Sleep.

---

## 10. Cognition Parameters

- **Recall**: Access to RAM/Volume/Bucket (Strength, Precision, Latency).
- **Inference**: Reasoning capabilities (Pattern Sensitivity, Causal Bias, Noise Tolerance).
- **Learning**: Extraction of lessons (Learning Rate, Generalization, Trauma Gain).

---

## 11. Cross-Universe Travel

Sleep allows consciousness to detach and travel to other universes (U1).
- **Dilation Factor D**: Time relativity mapping ($ \Delta t_{U1} = D \times \Delta t_{U0} $).
- **Selection**: Driven by zone weights, recency, and stress bias.
- **Identity Protection**: IdentityBleedRate is kept extremely low to preserve abstract lessons over identity overwrite.

---

## 12. MPD (Multi-Personal Disorder)

A rare failure mode triggered by repeated deep sleep failure and extreme fragmentation/stress.
- **Mechanism**: Abnormal increase in separation ($\gamma$) and decrease in core dominance ($\alpha$).

---

## Control Plane Controllers

The "laws" of the universe implemented as Kubernetes reconciliation loops:
1. **BindingController**: Credential-based consciousness attachment.
2. **MemoryController**: State flow management (RAM -> Volume -> Bucket).
3. **SleepController**: Scheduling and monitoring fragmentation/stress.
4. **LifecycleController**: Sequencing birth, death, and respawn.
5. **LuckController**: MacroLuck injection.
6. **PhysicsJitterController**: Managing zonal drift.
7. **ZoneController**: Social graph clustering and membership weighting.
8. **TravelController**: Managing cross-universe sessions and filtered memory bridges.
