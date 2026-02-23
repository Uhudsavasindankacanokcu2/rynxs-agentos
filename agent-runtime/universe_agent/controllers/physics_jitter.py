import random
import time
import logging
from typing import Dict, List, Optional
from ..models import Consciousness, PhysicsJitter

logger = logging.getLogger(__name__)

class PhysicsJitterController:
    """
    Implements Zonal and Global physics drift.
    Invariant: Drift is smooth and bounded.
    """
    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
            
        # Initial drift values for zones

        self.zonal_drifts: Dict[str, float] = {
            "family": 0.00005,
            "work": 0.00005,
            "friends": 0.00005,
            "community": 0.00005
        }
        self.global_jitter = 0.0
        self.last_update = time.time()
        
        # Constraints from spec
        self.min_jitter = 0.00001
        self.max_jitter = 0.0001
        self.drift_step = 0.000001

    def step(self):
        """Simulate slow drift ε_zone(t) over time."""
        for zone in self.zonal_drifts:
            change = random.uniform(-self.drift_step, self.drift_step)
            new_val = self.zonal_drifts[zone] + change
            # Bound drift
            self.zonal_drifts[zone] = max(self.min_jitter, min(self.max_jitter, new_val))

        # Rare global event
        if random.random() < 0.001:  # 0.1% chance per step
            self.global_jitter = random.uniform(0.0, 0.00005)
            logger.warning(f"[PHYSICS] Rare global jitter event: {self.global_jitter}")
        else:
            # Global jitter decays slowly
            self.global_jitter *= 0.95
            if self.global_jitter < 1e-8:
                self.global_jitter = 0

    def get_effective_jitter(self, consciousness: Consciousness) -> float:
        """
        ε_entity(t) = Σ pZ(u,t) * ε_zone(Z,t) + ε_global(t)
        """
        self.step() # Progressive drift
        
        effective = 0.0
        memberships = consciousness.state.zone_memberships
        
        if not memberships:
            return self.zonal_drifts["community"] + self.global_jitter
            
        for m in memberships:
            zonal_val = self.zonal_drifts.get(m.zone_id, self.zonal_drifts["community"])
            effective += m.weight * zonal_val
            
        final_val = effective + self.global_jitter
        logger.debug(f"[PHYSICS] Effective jitter for {consciousness.id}: {final_val}")
        return final_val
