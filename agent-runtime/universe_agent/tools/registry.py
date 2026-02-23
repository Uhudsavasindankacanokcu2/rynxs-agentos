from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]

class ToolRegistry:
    def __init__(self, tools: List[Tool]):
        self.tools = {t.name: t for t in tools}

    @staticmethod
    def default() -> "ToolRegistry":
        return ToolRegistry([
            Tool("fs.read","Read a file from the workspace",{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
            Tool("fs.write","Write a file to the workspace",{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}),
            Tool("http.fetch","Fetch a URL (stubbed in MVP)",{"type":"object","properties":{"url":{"type":"string"}},"required":["url"]}),
            Tool("sandbox.shell","Run a shell command (sandbox stub)",{"type":"object","properties":{"cmd":{"type":"string"}},"required":["cmd"]}),
        ])

    def as_openai_tools(self) -> List[Dict[str, Any]]:
        out = []
        for t in self.tools.values():
            out.append({"type":"function","function":{"name":t.name,"description":t.description,"parameters":t.parameters}})
        return out
