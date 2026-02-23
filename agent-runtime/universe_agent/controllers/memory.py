from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import json
import logging
from ..workspace import Workspace

logger = logging.getLogger(__name__)

class MemoryLayer(ABC):
    @abstractmethod
    def write(self, key: str, data: Any) -> Optional[str]:
        pass

    @abstractmethod
    def read(self, key: str) -> Optional[Any]:
        pass

class RAMLayer(MemoryLayer):
    """
    Volatile memory - live experience stream. 
    Path: /workspace/state/ram.json (for proof exposure, but wipes on death)
    """
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.path = self.workspace.path("state/ram.json")
        self.data: Dict[str, Any] = {}
        self._sync_to_disk()

    def _sync_to_disk(self):
        """Expose RAM to disk for 'proof' visibility."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def write(self, key: str, data: Any) -> Optional[str]:
        self.data[key] = data
        self._sync_to_disk()
        return None

    def read(self, key: str) -> Optional[Any]:
        return self.data.get(key)

    def wipe(self):
        self.data = {}
        self._sync_to_disk()

class VolumeLayer(MemoryLayer):
    """
    Persistent personal memory - survives pod death.
    Path: /workspace/state/volume.json
    """
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.path = self.workspace.path("state/volume.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, key: str, data: Any) -> Optional[str]:
        # We store everything in one persistent JSON for the volume in this stage
        current = self.load_all()
        current[key] = data
        self.path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return None


    def read(self, key: str) -> Optional[Any]:
        return self.load_all().get(key)

    def load_all(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except:
            return {}

import hashlib

class BucketLayer(MemoryLayer):
    """
    Snapshot/Archive memory - atomic checkpoints.
    Path: /workspace/state/bucket/snap-<ts>.json
    """
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.root = self.workspace.path("state/bucket")
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, tag: str, data: Any) -> str:
        """Atomic snapshot with immutability and hashing."""
        p = self.root / f"snap-{tag}.json"
        if p.exists():
            raise FileExistsError(f"Snapshot {tag} already exists. Immutability enforced.")
            
        content = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
        p.write_text(content, encoding="utf-8")
        
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        logger.info(f"[BUCKET] Snapshot created: {p.name} (SHA256: {sha256[:8]}...)")
        return sha256

    def read(self, tag: str) -> Optional[Any]:
        p = self.root / f"snap-{tag}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

class MemoryManager:
    def __init__(self, workspace: Workspace):
        self.ram = RAMLayer(workspace)
        self.volume = VolumeLayer(workspace)
        self.bucket = BucketLayer(workspace)

    def incremental_backup(self):
        """RAM -> Volume"""
        logger.info("[MEMORY] RAM to Volume incremental synchronization.")
        for key, val in self.ram.data.items():
            self.volume.write(key, val)

    def snapshot(self, tag: str) -> str:
        """Full state -> Bucket. Returns SHA256."""
        state = {
            "ram": self.ram.data,
            "volume": self.volume.load_all(),
            "t": tag
        }
        return self.bucket.write(tag, state)

