import hashlib, json, time
from typing import Any, Dict
from ..workspace import Workspace

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

def sha256_json(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return sha256_text(raw)

def write_audit(workspace: Workspace, event: Dict[str, Any]):
    workspace.append_jsonl("audit.jsonl", event)
