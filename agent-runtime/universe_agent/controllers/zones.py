import logging
from typing import List, Dict, Tuple
from ..models import Consciousness, Relationship, ZoneWeight

logger = logging.getLogger(__name__)

# Base weights for relationship types
RELATIONSHIP_BASE_WEIGHTS = {
    "parent-child": 1.0,
    "spouse": 1.0,
    "sibling": 0.8,
    "close-friend": 0.7,
    "coworker-team": 0.6,
    "friend": 0.4,
    "neighbor": 0.2,
    "acquaintance": 0.1,
}

class ZoneController:
    """
    Implements Social-Graph Sharding and Weighted Membership.
    Zones: Family, Work, Friends, Community
    """
    def __init__(self):
        self.zones = ["family", "work", "friends", "community"]

    def calculate_coupling(self, rel: Relationship) -> float:
        """
        C(u,v) = Base(type) × Intensity × Recency × Frequency × Stability × Trust × Obligation
        """
        base = RELATIONSHIP_BASE_WEIGHTS.get(rel.type, 0.1)
        coupling = (
            base * 
            rel.intensity * 
            rel.recency * 
            rel.frequency * 
            rel.stability * 
            rel.trust * 
            (1.0 + rel.obligation)
        )
        return coupling

    def map_relationship_to_zone(self, rel_type: str) -> str:
        """Simple mapping for MVP."""
        if rel_type in ["parent-child", "spouse", "sibling"]:
            return "family"
        if rel_type in ["coworker-team", "manager-report"]:
            return "work"
        if rel_type in ["close-friend", "friend"]:
            return "friends"
        return "community"

    def update_memberships(self, consciousness: Consciousness):
        """
        Calculate pZ = Affinity(u,Z) / Σ Affinity(u,all zones)
        """
        affinities = {z: 0.0 for z in self.zones}
        
        for rel in consciousness.relationships:
            coupling = self.calculate_coupling(rel)
            zone = self.map_relationship_to_zone(rel.type)
            affinities[zone] += coupling
            
        total_affinity = sum(affinities.values())
        
        if total_affinity == 0:
            # Default to community if no bonds exist
            consciousness.state.zone_memberships = [ZoneWeight(zone_id="community", weight=1.0)]
            return

        memberships = []
        for zone, affinity in affinities.items():
            if affinity > 0:
                weight = affinity / total_affinity
                memberships.append(ZoneWeight(zone_id=zone, weight=round(weight, 4)))
        
        # Sort by weight descending and keep top K (K=3)
        memberships.sort(key=lambda x: x.weight, reverse=True)
        top_memberships = memberships[:3]
        
        # Re-normalize if we truncated
        if len(memberships) > 3:
            new_total = sum(m.weight for m in top_memberships)
            for m in top_memberships:
                m.weight = float(round(m.weight / new_total, 4))
        
        consciousness.state.zone_memberships = top_memberships


        logger.info(f"[ZONES] Updated memberships for {consciousness.id}: {consciousness.state.zone_memberships}")
