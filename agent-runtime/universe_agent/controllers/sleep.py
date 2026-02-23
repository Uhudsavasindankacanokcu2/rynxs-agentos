import time
import logging
from ..models import Consciousness

logger = logging.getLogger(__name__)

class SleepController:
    """
    Implements upgraded Sleep triggers based on health metrics.
    FragmentationIndex (Frag) thresholds control sleep types.
    """
    def __init__(self, t1_threshold: float = 5.0, t2_threshold: float = 15.0):
        self.t1 = t1_threshold # Light sleep recommended
        self.t2 = t2_threshold # Deep sleep forced
        self.last_deep_sleep = time.time()
        
        # Coefficients
        self.a_ram = 0.5
        self.b_contradict = 2.0
        self.c_stress = 1.5
        self.d_time = 0.001

    def calculate_fragmentation(self, consciousness: Consciousness, ram_size: int) -> float:
        """
        Frag = a*ram_size + b*contradictions + c*stress + d*time_since_deep_sleep
        """
        # Simplified metrics for MVP
        stress = self._estimate_stress(consciousness)
        dt = time.time() - self.last_deep_sleep
        
        # We assume 0 contradictions for now
        frag = (self.a_ram * ram_size) + (self.c_stress * stress) + (self.d_time * dt)
        
        logger.debug(f"[SLEEP] Calculated Fragmentation: {frag:.2f} (Stress: {stress:.2f}, DT: {dt:.0f}s)")
        return frag

    def _estimate_stress(self, consciousness: Consciousness) -> float:
        """Stress = Average negative valence weighted by coupling."""
        # Simplified: count relationships with negative valence
        stress = 0.0
        for rel in consciousness.relationships:
            if rel.valence < 0:
                stress += abs(rel.valence) * rel.intensity
        return stress

    def get_sleep_recommendation(self, consciousness: Consciousness, ram_size: int) -> str:
        frag = self.calculate_fragmentation(consciousness, ram_size)
        
        if frag > self.t2:
            return "DEEP"
        if frag > self.t1:
            return "LIGHT"
        return "NONE"

    def record_deep_sleep(self):
        self.last_deep_sleep = time.time()
        logger.info("[SLEEP] Deep sleep record updated.")
