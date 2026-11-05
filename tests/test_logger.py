"""Tests for ai_file_rename.logger: session logging and global history."""

import csv
import json
from pathlib import Path

import pytest

from ai_file_rename.logger import CSV_LEDGER_COLUMNS, RenameLogger


class TestRenameLogger:
    def test_logger_creates_log_dir(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "test-001")
        assert log_dir.exists()

    def test_logger_creates_session_log(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "test-002")
        logger.info("Test message")

        assert logger.session_log.exists()
        content = logger.session_log.read_text()
        assert "Test message" in content

    def test_append_to_history(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "test-003")

        record = {
            "run_id": "test-003",
            "files_renamed": 5,
            "target_directory": "/tmp/test",
        }
        logger.append_to_history(record)

        assert logger.history_log.exists()
        with open(logger.history_log) as f:
            line = f.readline()
            data = json.loads(line)
        assert data["run_id"] == "test-003"
        assert data["files_renamed"] == 5

    def test_append_multiple_records(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "test-004")

        for i in range(5):
            logger.append_to_history({"run_id": f"run-{i}", "count": i})

        records = logger.query_history(last_n=10)
        assert len(records) == 5

    def test_query_history_last_n(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "test-005")

        for i in range(10):
            logger.append_to_history({"run_id": f"run-{i}"})

        records = logger.query_history(last_n=3)
        assert len(records) == 3
        # Should be the last 3
        assert records[-1]["run_id"] == "run-9"

    def test_query_history_filter_by_directory(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "test-006")

        logger.append_to_history({"run_id": "a", "target_directory": "/tmp/dir-a"})
        logger.append_to_history({"run_id": "b", "target_directory": "/tmp/dir-b"})
        logger.append_to_history({"run_id": "c", "target_directory": "/tmp/dir-a"})

        records = logger.query_history(directory=Path("/tmp/dir-a"))
        assert len(records) == 2
        assert all("dir-a" in r["target_directory"] for r in records)

    def test_query_empty_history(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "test-007")
        records = logger.query_history()
        assert records == []

    def test_log_levels(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "test-008", verbose=True)

        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warning msg")
        logger.error("error msg")

        content = logger.session_log.read_text()
        assert "debug msg" in content
        assert "info msg" in content
        assert "warning msg" in content
        assert "error msg" in content


class TestCsvLedger:
    """Tests for the CSV session ledger (append_to_csv_ledger / read_csv_ledger)."""

    def _make_row(self, run_id="run-001", **overrides):
        """Helper to build a realistic ledger row dict."""
        row = {
            "timestamp": "2026-02-26T10:00:00",
            "run_id": run_id,
            "target_directory": "/tmp/photos",
            "recursive": True,
            "total_files_discovered": 42,
            "total_folders_touched": 3,
            "files_renamed": 38,
            "files_skipped": 2,
            "files_failed": 2,
            "symlinks_updated": 1,
            "model_used": "gemini-2.5-flash",
            "estimated_tokens": 12500,
            "estimated_cost_usd": 0.03,
            "duration_seconds": 14.72,
        }
        row.update(overrides)
        return row

    def test_creates_file_with_header(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "csv-001")

        logger.append_to_csv_ledger(self._make_row())

        assert logger.ledger_csv.exists()
        with open(logger.ledger_csv, "r", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert header == CSV_LEDGER_COLUMNS

    def test_appends_single_row(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "csv-002")

        logger.append_to_csv_ledger(self._make_row(run_id="abc-123"))

        rows = logger.read_csv_ledger()
        assert len(rows) == 1
        assert rows[0]["run_id"] == "abc-123"
        assert rows[0]["files_renamed"] == "38"  # CSV values are strings

    def test_appends_multiple_rows_without_duplicate_header(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "csv-003")

        for i in range(5):
            logger.append_to_csv_ledger(self._make_row(run_id=f"run-{i}"))

        # Read raw text and confirm only one header line
        raw = logger.ledger_csv.read_text()
        header_line = ",".join(CSV_LEDGER_COLUMNS)
        assert raw.count(header_line) == 1

        rows = logger.read_csv_ledger()
        assert len(rows) == 5
        assert rows[0]["run_id"] == "run-0"
        assert rows[4]["run_id"] == "run-4"

    def test_read_csv_ledger_filter_by_directory(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "csv-004")

        logger.append_to_csv_ledger(
            self._make_row(run_id="a", target_directory="/tmp/dir-a")
        )
        logger.append_to_csv_ledger(
            self._make_row(run_id="b", target_directory="/tmp/dir-b")
        )
        logger.append_to_csv_ledger(
            self._make_row(run_id="c", target_directory="/tmp/dir-a")
        )

        rows = logger.read_csv_ledger(directory=Path("/tmp/dir-a"))
        assert len(rows) == 2
        assert all("dir-a" in r["target_directory"] for r in rows)

    def test_read_csv_ledger_last_n(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "csv-005")

        for i in range(10):
            logger.append_to_csv_ledger(self._make_row(run_id=f"run-{i}"))

        rows = logger.read_csv_ledger(last_n=3)
        assert len(rows) == 3
        assert rows[-1]["run_id"] == "run-9"

    def test_read_csv_ledger_empty_file(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "csv-006")

        rows = logger.read_csv_ledger()
        assert rows == []

    def test_missing_keys_default_to_empty_string(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "csv-007")

        # Only supply a few keys
        logger.append_to_csv_ledger({"run_id": "sparse", "files_renamed": 1})

        rows = logger.read_csv_ledger()
        assert len(rows) == 1
        assert rows[0]["run_id"] == "sparse"
        assert rows[0]["timestamp"] == ""
        assert rows[0]["model_used"] == ""

    def test_csv_is_valid_rfc4180(self, temp_dir):
        """Ensure the CSV is well-formed and openable by any spreadsheet app."""
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "csv-008")

        # Directory with commas and quotes to exercise quoting
        logger.append_to_csv_ledger(
            self._make_row(
                target_directory='/tmp/"tricky, dir"',
            )
        )

        # Re-parse with the csv module to prove round-trip fidelity
        with open(logger.ledger_csv, "r", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["target_directory"] == '/tmp/"tricky, dir"'

    def test_read_csv_ledger_combined_filters(self, temp_dir):
        log_dir = temp_dir / "logs"
        logger = RenameLogger(log_dir, "csv-009")

        for i in range(6):
            td = "/tmp/alpha" if i % 2 == 0 else "/tmp/beta"
            logger.append_to_csv_ledger(
                self._make_row(run_id=f"run-{i}", target_directory=td)
            )

        # 3 rows match /tmp/alpha (indices 0, 2, 4); ask for last 2
        rows = logger.read_csv_ledger(directory=Path("/tmp/alpha"), last_n=2)
        assert len(rows) == 2
        assert rows[0]["run_id"] == "run-2"
        assert rows[1]["run_id"] == "run-4"
