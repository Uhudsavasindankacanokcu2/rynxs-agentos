import os
import requests
from typing import Any, Dict, List
from .base import Provider

class LocalOpenAICompat(Provider):
    def __init__(self, cfg: Dict[str, Any]):
        self.base = cfg.get("baseUrl", "http://localhost:8080").rstrip("/")
        self.model = cfg.get("model", "gpt-oss")
        self.api_key = os.getenv("LLM_API_KEY", "")

    def plan(self, user_text: str, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an agent. If you need tools, use tool calls. Otherwise reply succinctly."},
                {"role": "user", "content": user_text},
            ],
            "tools": tools,
        }
        r = requests.post(f"{self.base}/v1/chat/completions", json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0]["message"]
        return {"tool_calls": msg.get("tool_calls", []) or [], "raw": msg}

    def respond(self, user_text: str, tool_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"text": "OK", "tool_results": tool_results}
