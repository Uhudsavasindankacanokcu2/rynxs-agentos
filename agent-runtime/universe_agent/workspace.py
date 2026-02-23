from dataclasses import dataclass
from pathlib import Path
import json

@dataclass
class Workspace:
    root: Path

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise PermissionError("Path escapes workspace")
        return p

    def append_jsonl(self, rel: str, obj: dict):
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj) + "\n")
