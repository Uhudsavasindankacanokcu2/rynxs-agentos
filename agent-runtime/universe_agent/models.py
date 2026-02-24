from typing import List, Dict, Optional, Tuple
import time

class MemoryAccessPolicy:
    def __init__(self, ram: bool = True, volume: bool = True, bucket: bool = True):
        self.ram = ram
        self.volume = volume
        self.bucket = bucket

class CognitionParams:
    def __init__(self, recall_strength: float = 1.0, recall_precision: float = 1.0, recall_latency: float = 0.1, state_access: Optional[MemoryAccessPolicy] = None, pattern_sensitivity: float = 1.0, causal_bias: float = 0.5, noise_tolerance: float = 0.5, learning_rate: float = 0.01, generalization: float = 0.5, trauma_gain: float = 1.0):
        self.recall_strength = recall_strength
        self.recall_precision = recall_precision
        self.recall_latency = recall_latency
        self.state_access = state_access if state_access is not None else MemoryAccessPolicy()
        self.pattern_sensitivity = pattern_sensitivity
        self.causal_bias = causal_bias
        self.noise_tolerance = noise_tolerance
        self.learning_rate = learning_rate
        self.generalization = generalization
        self.trauma_gain = trauma_gain

class Relationship:
    def __init__(self, target_id: str, type: str, intensity: float = 0.5, recency: float = 1.0, frequency: float = 1.0, stability: float = 1.0, trust: float = 0.5, obligation: float = 0.0, valence: float = 0.0):
        self.target_id = target_id
        self.type = type
        self.intensity = intensity
        self.recency = recency
        self.frequency = frequency
        self.stability = stability
        self.trust = trust
        self.obligation = obligation
        self.valence = valence

class ZoneWeight:
    def __init__(self, zone_id: str, weight: float):
        self.zone_id = zone_id
        self.weight = weight

class SubPersona:
    def __init__(self, id: str, name: str, context_zone_ids: List[str], traits: Dict[str, float]):
        self.id = id
        self.name = name
        self.context_zone_ids = context_zone_ids
        self.traits = traits

class EntityState:
    def __init__(self, core_dominance: float = 0.8, flexibility: float = 0.5, separation: float = 0.3, active_persona_id: Optional[str] = None, zone_memberships: Optional[List[ZoneWeight]] = None):
        self.core_dominance = core_dominance
        self.flexibility = flexibility
        self.separation = separation
        self.active_persona_id = active_persona_id
        self.zone_memberships = zone_memberships if zone_memberships is not None else []

class PhysicsJitter:
    def __init__(self, value: float, drift_rate: float = 0.0001):
        self.value = value
        self.drift_rate = drift_rate

class Consciousness:
    def __init__(self, id: str, name: str, cognition: Optional[CognitionParams] = None, state: Optional[EntityState] = None, relationships: Optional[List[Relationship]] = None):
        self.id = id
        self.name = name
        self.cognition = cognition if cognition is not None else CognitionParams()
        self.state = state if state is not None else EntityState()
        self.relationships = relationships if relationships is not None else []
