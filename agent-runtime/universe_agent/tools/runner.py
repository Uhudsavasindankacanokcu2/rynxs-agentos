import json
import time
from typing import Any, Dict
from ..workspace import Workspace
from ..policy import UniversePolicy
from .audit import write_audit, sha256_json, sha256_text
from .sandbox_k8s import SandboxK8s

class ToolRunner:
    def __init__(self, workspace: Workspace, policy: UniversePolicy, agent_name: str = "agent", namespace: str = "universe"):
        self.workspace = workspace
        self.policy = policy
        self.agent_name = agent_name
        self.namespace = namespace
        self.sandbox = SandboxK8s(namespace)

    def run(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        fn = tool_call.get("function", {})
        name = fn.get("name")
        args_raw = fn.get("arguments", "{}")

        args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
        args_hash = sha256_json(args)

        try:
            self.policy.check_tool_allowed(name)
        except Exception as e:
            write_audit(self.workspace, {
                "t": time.time(),
                "agent": self.agent_name,
                "ns": self.namespace,
                "tool": name,
                "allowed": False,
                "reason": str(e),
                "args_sha256": args_hash,
            })
            raise

        if name == "fs.read":
            p = self.workspace.path(args["path"])
            out = p.read_text(encoding="utf-8") if p.exists() else ""
            write_audit(self.workspace, {
                "t": time.time(),
                "agent": self.agent_name,
                "ns": self.namespace,
                "tool": name,
                "allowed": True,
                "args_sha256": args_hash,
            })
            return {"tool": name, "ok": True, "content": out}

        if name == "fs.write":
            p = self.workspace.path(args["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], encoding="utf-8")
            write_audit(self.workspace, {
                "t": time.time(),
                "agent": self.agent_name,
                "ns": self.namespace,
                "tool": name,
                "allowed": True,
                "args_sha256": args_hash,
            })
            return {"tool": name, "ok": True}

        if name == "http.fetch":
            # Stub for audit
            write_audit(self.workspace, {
                "t": time.time(),
                "agent": self.agent_name,
                "ns": self.namespace,
                "tool": name,
                "allowed": True,
                "args_sha256": args_hash,
            })
            return {"tool": name, "ok": True, "note": "stubbed in MVP"}

        if name == "sandbox.shell":
            job_name, out = self.sandbox.run_shell(args["cmd"])
            write_audit(self.workspace, {
                "t": time.time(),
                "agent": self.agent_name,
                "ns": self.namespace,
                "tool": name,
                "allowed": True,
                "args_sha256": args_hash,
                "sandbox_job": job_name,
                "stdout_sha256": sha256_text(out),
                "stdout_preview": out[:200],
            })
            return {"tool": name, "ok": True, "stdout": out, "job": job_name}

        return {"tool": name, "ok": False, "error": "unknown tool"}
