# Universe Model Phase 2: Dynamics & Zones

Building on the v0.1 primitives, Phase 2 introduces social sharding, variable physics, and advanced lifecycle control.

## 1. Social Graph & Zones
Entities are no longer isolated; they exist within a social topology.

### Relationship Schema
- **type**: parent-child, spouse, coworker, friend, neighbor, etc.
- **metrics**: intensity, recency, frequency, stability, trust, obligation, valence.

### Coupling Function $C$
$$C(u,v) = Base(type) \times intensity \times recency \times frequency \times stability \times trust \times obligation$$

### Zone Membership
Entities have weighted memberships in multiple zones:
- `Affinity(u, Z) = Σ C(u,v)` for all $v \in Z$.
- `p_Z = Affinity(u, Z) / Σ Affinity(u, all zones)`.

---

## 2. Physics Jitter Controller
Environmental rules are not static; they drift within boundaries.

### Zonal Drift ($\epsilon_{zone}$)
- Drift range: $[1e-5, 1e-4]$.
- Smooth, continuous drift.

### Global Events ($\epsilon_{global}$)
- Rare, high-impact "epoch" events affecting all zones simultaneously.

### Effective Influence
$$\epsilon_{entity}(t) = \Sigma pZ(u,t) \times \epsilon_{zone}(Z,t) + \epsilon_{global}(t)$$

---

## 3. Luck Controller
The macro-luck layer introduces narrative variability.
- **macroLuckRate**: $\in [0.01, 0.10]$.
- **Injected into**: Encounter routing and event selection.

---

## 4. Advanced Sleep Control
Sleep triggers are now driven by a state health metric.

### Fragmentation Index ($Frag$)
$$Frag = a \times ram\_size + b \times contradictions + c \times stress + d \times time\_since\_deep\_sleep$$

### Thresholds
- **$T_1$ (Light Sleep)**: Recommended backup.
- **$T_2$ (Deep Sleep)**: Forced snapshot and compaction.

---

## 5. Travel (U1) Hooks
Stubs for cross-universe travel.
- `select_universe()`: Probability distribution based on zone weights and stress.
- `run_session()`: Dilation-aware execution.
- `bridge()`: Filtered memory transfer.
