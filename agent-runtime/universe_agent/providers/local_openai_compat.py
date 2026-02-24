
import os
import urllib.request
import urllib.error
import json
import logging
from typing import Any, Dict, List
from .base import Provider

# Set up a logger for this module
logger = logging.getLogger(__name__)

class LocalOpenAICompat(Provider):
    """
    A provider that connects to a local, OpenAI-compatible API endpoint.
    It is designed to be resilient to configuration and network errors,
    allowing the agent to run in a "degraded" mode if the LLM is unavailable.
    """
    def __init__(self, cfg: Dict[str, Any]):
        self._ready = False
        self.kind = cfg.get("kind", "local_openai_compat")
        
        try:
            self.base = cfg.get("baseUrl", "http://localhost:8080").rstrip("/")
            self.model = cfg.get("model", "gpt-oss")
            self.api_key = os.getenv("LLM_API_KEY", "dummy-key") # Use a dummy key if not set
            
            # Perform a quick health check on initialization
            self._health_check()
            self._ready = True
            logger.info(f"LocalOpenAICompat provider initialized successfully for model '{self.model}' at {self.base}")

        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.warning(
                f"Could not connect to local LLM endpoint at {self.base}. "
                f"Provider will be in a degraded state. Error: {e}"
            )
        except Exception as e:
            logger.error(
                f"An unexpected error occurred during LocalOpenAICompat initialization. "
                f"Provider will be in a degraded state. Error: {e}",
                exc_info=True # Include stack trace for debugging
            )

    def _health_check(self):
        """Performs a simple request to check if the endpoint is available."""
        req = urllib.request.Request(f"{self.base}/v1", method="OPTIONS")
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status >= 400:
                raise urllib.error.HTTPError(self.base, response.status, "Health check failed", response.headers, None)

    def is_ready(self) -> bool:
        """Returns True if the provider was initialized successfully and is ready to use."""
        return self._ready

    def plan(self, user_text: str, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.is_ready():
            logger.warning("plan() called but provider is not ready. Returning empty plan.")
            return {"tool_calls": [], "raw": {}}

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an agent. If you need tools, use tool calls. Otherwise reply succinctly."},
                {"role": "user", "content": user_text},
            ],
            "tools": tools,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{self.base}/v1/chat/completions", data=req_data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                if response.status >= 400:
                     logger.error(f"LLM request failed with status {response.status}: {response.read().decode('utf-8', 'ignore')}")
                     return {"tool_calls": [], "raw": {}}

                resp_body = response.read().decode("utf-8")
                resp_data = json.loads(resp_body)
                msg = resp_data["choices"][0]["message"]
                return {"tool_calls": msg.get("tool_calls", []) or [], "raw": msg}
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"LLM request or response processing failed: {e}")
            return {"tool_calls": [], "raw": {}} # Return empty plan on failure

    def respond(self, user_text: str, tool_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        # This method is a stub and might need more logic depending on the agent's needs
        if not self.is_ready():
            return {"text": "Provider is not available.", "tool_results": tool_results}
            
        return {"text": "OK", "tool_results": tool_results}
