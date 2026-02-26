"""
Ephemeral state manager for ai-file-rename.

Manages the working manifest file (.ai-rename-manifest.json) that enables:
- Crash recovery (resume interrupted operations)
- Undo (reverse completed operations)
- Multi-instance conflict detection

The manifest is written atomically (write-to-temp, then os.replace).
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from ai_file_rename.models import ValidatedRename


class Manifest:
    """Manages the ephemeral manifest file for a rename operation."""

    FILENAME = ".ai-rename-manifest.json"

    def __init__(self, directory: Path, run_id: str):
        self.directory = directory.resolve()
        self.path = self.directory / self.FILENAME
        self.run_id = run_id
        self._data: dict = {}

    def create(self, renames: list[ValidatedRename]) -> None:
        """Create the manifest with all renames in 'pending' status."""
        self._data = {
            "version": "1.0",
            "run_id": self.run_id,
            "started_at": datetime.now().isoformat(),
            "target_directory": str(self.directory),
            "status": "in_progress",
            "renames": [],
        }

        for i, rename in enumerate(renames):
            self._data["renames"].append({
                "index": i,
                "old_name": rename.original.current_name,
                "new_name": rename.final_name,
                "old_path": str(rename.original.current_path),
                "new_path": str(rename.original.current_path.parent / rename.final_name),
                "file_size_bytes": rename.original.current_path.stat().st_size
                    if rename.original.current_path.exists() else 0,
                "status": "pending",
                "completed_at": None,
                "error": None,
            })

        self.flush()

    def record_intent(self, index: int) -> None:
        """Mark a rename as 'in_progress' before executing."""
        if index < len(self._data["renames"]):
            self._data["renames"][index]["status"] = "in_progress"
            self.flush()

    def record_success(self, index: int) -> None:
        """Mark a rename as 'completed' after verification."""
        if index < len(self._data["renames"]):
            self._data["renames"][index]["status"] = "completed"
            self._data["renames"][index]["completed_at"] = datetime.now().isoformat()
            self.flush()

    def record_failure(self, index: int, error: str) -> None:
        """Mark a rename as 'failed' with error details."""
        if index < len(self._data["renames"]):
            self._data["renames"][index]["status"] = "failed"
            self._data["renames"][index]["error"] = error
            self._data["renames"][index]["completed_at"] = datetime.now().isoformat()
            self.flush()

    def mark_complete(self) -> None:
        """Mark the entire manifest as completed."""
        self._data["status"] = "completed"
        self._data["completed_at"] = datetime.now().isoformat()
        self.flush()

    def flush(self) -> None:
        """
        Force write to disk using atomic write pattern.

        Writes to a temp file first, then os.replace() to the final path.
        Calls os.fsync() to ensure data reaches disk.
        """
        content = json.dumps(self._data, indent=2, default=str)

        # Write to temp file in the same directory (same filesystem for atomic replace)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.directory),
            prefix=".ai-rename-manifest-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, str(self.path))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def cleanup(self) -> None:
        """Delete the manifest file (called on successful completion)."""
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    @classmethod
    def load_existing(cls, directory: Path) -> Optional["Manifest"]:
        """
        Load an existing manifest from a previous run.

        Returns None if no manifest exists.
        """
        directory = directory.resolve()
        manifest_path = directory / cls.FILENAME

        if not manifest_path.exists():
            return None

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        run_id = data.get("run_id", "unknown")
        manifest = cls(directory, run_id)
        manifest._data = data
        return manifest

    @property
    def is_complete(self) -> bool:
        """True if all renames are completed."""
        if not self._data.get("renames"):
            return False
        return all(
            r["status"] == "completed" for r in self._data["renames"]
        )

    @property
    def is_interrupted(self) -> bool:
        """True if some renames are pending/in_progress (crash recovery needed)."""
        if not self._data.get("renames"):
            return False
        statuses = {r["status"] for r in self._data["renames"]}
        return "pending" in statuses or "in_progress" in statuses

    @property
    def data(self) -> dict:
        """Access the raw manifest data."""
        return self._data

    @property
    def completed_renames(self) -> list[dict]:
        """Return list of completed rename entries."""
        return [
            r for r in self._data.get("renames", [])
            if r["status"] == "completed"
        ]

    @property
    def pending_renames(self) -> list[dict]:
        """Return list of pending rename entries."""
        return [
            r for r in self._data.get("renames", [])
            if r["status"] in ("pending", "in_progress")
        ]

    @property
    def failed_renames(self) -> list[dict]:
        """Return list of failed rename entries."""
        return [
            r for r in self._data.get("renames", [])
            if r["status"] == "failed"
        ]
