"""
Dual-level logging for ai-file-rename.

Manages both per-session log files and the global rename history (JSONL),
plus a CSV session ledger for spreadsheet-friendly reporting.
Uses file locking for multi-instance safety when writing to shared files.
"""

import csv
import io
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# Column order for the CSV session ledger.
CSV_LEDGER_COLUMNS = [
    "timestamp",
    "run_id",
    "target_directory",
    "recursive",
    "total_files_discovered",
    "total_folders_touched",
    "files_renamed",
    "files_skipped",
    "files_failed",
    "symlinks_updated",
    "model_used",
    "estimated_tokens",
    "estimated_cost_usd",
    "duration_seconds",
]


def _lock_file(f):
    """Acquire an exclusive lock on a file."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)


def _unlock_file(f):
    """Release a file lock."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class RenameLogger:
    """Manages session logging and global rename history."""

    def __init__(self, log_dir: Path, run_id: str, verbose: bool = False):
        self.log_dir = log_dir
        self.run_id = run_id
        self.session_log = log_dir / f"session-{run_id}.log"
        self.history_log = log_dir / "rename-history.jsonl"
        self.ledger_csv = log_dir / "session-ledger.csv"

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Set up Python logger
        self._logger = logging.getLogger(f"ai-rename.{run_id}")
        self._logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        self._logger.handlers.clear()

        # File handler: always DEBUG level for full trace.
        # delay=True defers file creation until the first log message,
        # preventing 0-byte orphan files from aborted sessions (ISSUE-06).
        file_handler = logging.FileHandler(self.session_log, encoding="utf-8", delay=True)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self._logger.addHandler(file_handler)

        # Console handler: respects verbose flag
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        console_handler.setFormatter(
            logging.Formatter("%(message)s")
        )
        self._logger.addHandler(console_handler)

    def info(self, message: str) -> None:
        self._logger.info(message)

    def warning(self, message: str) -> None:
        self._logger.warning(message)

    def error(self, message: str) -> None:
        self._logger.error(message)

    def debug(self, message: str) -> None:
        self._logger.debug(message)

    def append_to_history(self, record: dict) -> None:
        """
        Append a completed execution result to the global history log.

        Uses file locking for multi-instance safety.
        """
        line = json.dumps(record, default=str) + "\n"

        with open(self.history_log, "a", encoding="utf-8") as f:
            _lock_file(f)
            try:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
            finally:
                _unlock_file(f)

    def query_history(
        self,
        directory: Optional[Path] = None,
        last_n: int = 10,
    ) -> list[dict]:
        """
        Query the global history log with optional filters.

        Args:
            directory: Filter by target directory path.
            last_n: Return the last N entries.

        Returns:
            List of history records (most recent last).
        """
        if not self.history_log.exists():
            return []

        records = []
        with open(self.history_log, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if directory is not None:
                    target = record.get("target_directory", "")
                    if str(directory) not in target:
                        continue

                records.append(record)

        # Return last N
        return records[-last_n:]

    def append_to_csv_ledger(self, row: dict) -> None:
        """
        Append a single session row to the CSV session ledger.

        Creates the file with a header row if it does not yet exist.
        Uses file locking (same pattern as ``append_to_history``) so
        concurrent rename runs do not corrupt the file.

        Args:
            row: Dict whose keys match ``CSV_LEDGER_COLUMNS``.
                 Missing keys are written as empty strings.
        """
        needs_header = not self.ledger_csv.exists()

        # Build one CSV row into an in-memory buffer so we can write it
        # atomically while the lock is held.
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=CSV_LEDGER_COLUMNS,
            extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL,
        )

        if needs_header:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in CSV_LEDGER_COLUMNS})
        payload = buf.getvalue()

        with open(self.ledger_csv, "a", encoding="utf-8", newline="") as f:
            _lock_file(f)
            try:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            finally:
                _unlock_file(f)

    def read_csv_ledger(
        self,
        directory: Optional[Path] = None,
        last_n: Optional[int] = None,
    ) -> list[dict]:
        """
        Read the CSV session ledger and return rows as a list of dicts.

        Args:
            directory: If provided, only return rows whose
                       ``target_directory`` contains this path string.
            last_n: If provided, return only the last *N* matching rows.

        Returns:
            List of dicts keyed by ``CSV_LEDGER_COLUMNS`` (most recent last).
        """
        if not self.ledger_csv.exists():
            return []

        rows: list[dict] = []
        with open(self.ledger_csv, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if directory is not None:
                    target = row.get("target_directory", "")
                    if str(directory) not in target:
                        continue
                rows.append(row)

        if last_n is not None:
            rows = rows[-last_n:]

        return rows
