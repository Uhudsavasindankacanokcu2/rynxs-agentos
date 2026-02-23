import time
import logging
from typing import Optional
from .memory import MemoryManager
from ..workspace import Workspace
from ..models import Consciousness

logger = logging.getLogger(__name__)

class EntityLifecycle:
    def __init__(self, workspace: Workspace, consciousness: Consciousness):
        self.workspace = workspace
        self.consciousness = consciousness
        self.memory = MemoryManager(workspace)
        self.is_alive = False

    def birth(self):
        """spawn pod (Entity instance)."""
        logger.info(f"[BIRTH] Entity {self.consciousness.id} ({self.consciousness.name}) is born.")
        self.is_alive = True
        self.respawn()

    def awake_loop(self):
        """event-driven state updates (RAM grows)."""
        if not self.is_alive:
            return
        
        # Simulating experience stream
        self.memory.ram.write("last_awake_t", time.time())
        exp = self.memory.ram.read("experience_count") or 0
        self.memory.ram.write("experience_count", exp + 1)

    def light_sleep(self):
        """RAM housekeeping + incremental writes (to Volume)."""
        logger.info("[SLEEP] Light sleep triggered.")
        self.memory.incremental_backup()

    def deep_sleep(self):
        """compaction + atomic snapshot (to Bucket)."""
        logger.info("[SLEEP] Deep sleep triggered. Consolidating state.")
        self.memory.snapshot(tag=str(int(time.time())))

    def death(self):
        """detach consciousness; RAM wiped."""
        logger.warning(f"[DEATH] Entity {self.consciousness.id} has died. RAM wiped.")
        self.memory.ram.wipe()
        self.is_alive = False

    def respawn(self):
        """new pod appears; rebind + restore."""
        logger.info(f"[RESPAWN] Rebinding consciousness {self.consciousness.id}...")
        
        # Restore from Volume if exists
        state_data = self.memory.volume.load_all()
        if state_data:
            last_t = state_data.get("last_awake_t")
            logger.info(f"[RESTORE] Recovered state from Volume (last seen: {last_t})")
            # Restore relevant keys to RAM for continuity
            for k, v in state_data.items():
                self.memory.ram.write(k, v)
        else:
            logger.info("[RESTORE] No persistent state found. Fresh start.")
        
        self.is_alive = True
