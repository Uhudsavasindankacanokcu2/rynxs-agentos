from abc import ABC, abstractmethod
from typing import Any, Dict, List

class Provider(ABC):
    @abstractmethod
    def plan(self, user_text: str, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def respond(self, user_text: str, tool_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        ...
