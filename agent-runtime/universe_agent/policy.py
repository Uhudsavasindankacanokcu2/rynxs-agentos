from dataclasses import dataclass
from typing import Dict, Any, Set

@dataclass
class UniversePolicy:
    identity_bleed_rate: float
    allowed_tools: Set[str]
    egress_allowlist: Set[str]

    @staticmethod
    def from_agent_spec(agent_spec: Dict[str, Any]) -> "UniversePolicy":
        allowed = set(agent_spec.get("tools", {}).get("allow", []))
        bleed = float(agent_spec.get("identityBleedRate", 0.0005))
        egress = set(agent_spec.get("network", {}).get("allowEgressTo", []))
        return UniversePolicy(identity_bleed_rate=bleed, allowed_tools=allowed, egress_allowlist=egress)

    def check_tool_allowed(self, tool_name: str):
        if tool_name not in self.allowed_tools:
            raise PermissionError(f"Tool not allowed by policy: {tool_name}")
