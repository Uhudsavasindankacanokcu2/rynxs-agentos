"""
Checkpoint storage management.

Checkpoints are stored as separate JSON files in checkpoints/ directory.
Naming: cp_{event_index}_{event_hash_prefix}.json
"""

import os
import json
from pathlib import Path
from typing import List, Optional
from .model import Checkpoint


class CheckpointStore:
    """
    Manage checkpoint files on disk.

    Storage format:
    - checkpoints/ directory
    - Each file: cp_{event_index}_{event_hash_prefix}.json
    - Contents: Checkpoint JSON
    """

    def __init__(self, directory: str = "checkpoints"):
        """
        Initialize checkpoint store.

        Args:
            directory: Directory to store checkpoints
        """
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, checkpoint: Checkpoint) -> str:
        """
        Save checkpoint to disk.

        Args:
            checkpoint: Checkpoint to save

        Returns:
            Path to saved checkpoint file
        """
        # Generate filename
        event_hash_prefix = checkpoint.event_hash[:8]
        filename = f"cp_{checkpoint.event_index}_{event_hash_prefix}.json"
        filepath = self.directory / filename

        # Write checkpoint JSON
        with open(filepath, "w") as f:
            f.write(checkpoint.to_json())

        return str(filepath)

    def load(self, filepath: str) -> Checkpoint:
        """
        Load checkpoint from file.

        Args:
            filepath: Path to checkpoint file

        Returns:
            Checkpoint instance
        """
        with open(filepath, "r") as f:
            json_str = f.read()

        return Checkpoint.from_json(json_str)

    def list_checkpoints(self) -> List[str]:
        """
        List all checkpoint files in directory.

        Returns:
            List of checkpoint file paths (sorted by event_index)
        """
        checkpoint_files = []

        for filepath in self.directory.glob("cp_*.json"):
            checkpoint_files.append(str(filepath))

        # Sort by event_index (extract from filename)
        def extract_index(path: str) -> int:
            filename = os.path.basename(path)
            # cp_{index}_{hash}.json
            parts = filename.split("_")
            return int(parts[1])

        checkpoint_files.sort(key=extract_index)
        return checkpoint_files

    def find_latest(self) -> Optional[str]:
        """
        Find latest checkpoint (highest event_index).

        Returns:
            Path to latest checkpoint, or None if no checkpoints exist
        """
        checkpoints = self.list_checkpoints()
        if not checkpoints:
            return None
        return checkpoints[-1]

    def find_at_or_before(self, event_index: int) -> Optional[str]:
        """
        Find checkpoint at or before given event_index.

        Useful for fast replay: load checkpoint closest to target.

        Args:
            event_index: Target event index

        Returns:
            Path to checkpoint, or None if no suitable checkpoint found
        """
        checkpoints = self.list_checkpoints()

        # Find largest event_index <= target
        best = None
        for cp_path in checkpoints:
            cp = self.load(cp_path)
            if cp.event_index <= event_index:
                best = cp_path
            else:
                break  # Checkpoints are sorted

        return best

    def delete(self, filepath: str) -> None:
        """
        Delete checkpoint file.

        Args:
            filepath: Path to checkpoint file
        """
        os.remove(filepath)

    def rotate(self, keep_count: int = 10) -> None:
        """
        Rotate checkpoints, keeping only latest N.

        Args:
            keep_count: Number of checkpoints to keep
        """
        checkpoints = self.list_checkpoints()

        # Delete old checkpoints
        if len(checkpoints) > keep_count:
            to_delete = checkpoints[: len(checkpoints) - keep_count]
            for cp_path in to_delete:
                self.delete(cp_path)
