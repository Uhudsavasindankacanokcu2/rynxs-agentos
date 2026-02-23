from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel, Field
import time

class MemoryAccessPolicy(BaseModel):
    ram: bool = True
    volume: bool = True
    bucket: bool = True

class CognitionParams(BaseModel):
    recall_strength: float = 1.0
    recall_precision: float = 1.0
    recall_latency: float = 0.1
    state_access: MemoryAccessPolicy = Field(default_factory=MemoryAccessPolicy)
    
    pattern_sensitivity: float = 1.0
    causal_bias: float = 0.5
    noise_tolerance: float = 0.5
    
    learning_rate: float = 0.01
    generalization: float = 0.5
    trauma_gain: float = 1.0

class Relationship(BaseModel):
    target_id: str
    type: str  # family, friend, work, neighbor, etc.
    intensity: float = 0.5
    recency: float = 1.0
    frequency: float = 1.0
    stability: float = 1.0
    trust: float = 0.5
    obligation: float = 0.0
    valence: float = 0.0  # -1 to +1

class ZoneWeight(BaseModel):
    zone_id: str
    weight: float

class SubPersona(BaseModel):
    id: str
    name: str
    context_zone_ids: List[str]
    traits: Dict[str, float]

class EntityState(BaseModel):
    core_dominance: float = 0.8
    flexibility: float = 0.5
    separation: float = 0.3
    active_persona_id: Optional[str] = None
    zone_memberships: List[ZoneWeight] = Field(default_factory=list)

class PhysicsJitter(BaseModel):
    value: float
    drift_rate: float = 0.0001

class Consciousness(BaseModel):
    id: str
    name: str
    cognition: CognitionParams = Field(default_factory=CognitionParams)
    state: EntityState = Field(default_factory=EntityState)
    relationships: List[Relationship] = Field(default_factory=list)
