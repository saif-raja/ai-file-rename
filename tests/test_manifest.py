"""Tests for ai_file_rename.manifest: ephemeral state management."""

import json
from pathlib import Path

import pytest

from ai_file_rename.manifest import Manifest
from ai_file_rename.models import ProposedRename, ValidatedRename


def _make_validated(current: str, proposed: str, parent: Path) -> ValidatedRename:
    """Helper to create a ValidatedRename."""
    return ValidatedRename(
        original=ProposedRename(
            current_name=current,
            proposed_name=proposed,
            current_path=parent / current,
            proposed_path=parent / proposed,
            reasoning="test",
            confidence=0.9,
        ),
        final_name=proposed,
    )


class TestManifestLifecycle:
    def test_create_manifest(self, temp_dir):
        # Create actual files so stat() works
        (temp_dir / "a.txt").write_text("hello")
        (temp_dir / "b.txt").write_text("world")

        manifest = Manifest(temp_dir, "test-run-001")
        renames = [
            _make_validated("a.txt", "file-alpha.txt", temp_dir),
            _make_validated("b.txt", "file-beta.txt", temp_dir),
        ]
        manifest.create(renames)

        assert manifest.path.exists()
        assert manifest.is_interrupted  # All pending
        assert not manifest.is_complete

    def test_record_intent(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        manifest = Manifest(temp_dir, "test-run-002")
        renames = [_make_validated("a.txt", "new-a.txt", temp_dir)]
        manifest.create(renames)

        manifest.record_intent(0)
        assert manifest._data["renames"][0]["status"] == "in_progress"

    def test_record_success(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        manifest = Manifest(temp_dir, "test-run-003")
        renames = [_make_validated("a.txt", "new-a.txt", temp_dir)]
        manifest.create(renames)

        manifest.record_intent(0)
        manifest.record_success(0)

        assert manifest._data["renames"][0]["status"] == "completed"
        assert manifest._data["renames"][0]["completed_at"] is not None

    def test_record_failure(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        manifest = Manifest(temp_dir, "test-run-004")
        renames = [_make_validated("a.txt", "new-a.txt", temp_dir)]
        manifest.create(renames)

        manifest.record_failure(0, "Permission denied")

        assert manifest._data["renames"][0]["status"] == "failed"
        assert "Permission denied" in manifest._data["renames"][0]["error"]

    def test_is_complete_when_all_done(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        (temp_dir / "b.txt").write_text("world")

        manifest = Manifest(temp_dir, "test-run-005")
        renames = [
            _make_validated("a.txt", "new-a.txt", temp_dir),
            _make_validated("b.txt", "new-b.txt", temp_dir),
        ]
        manifest.create(renames)

        manifest.record_success(0)
        manifest.record_success(1)

        assert manifest.is_complete

    def test_cleanup_removes_file(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        manifest = Manifest(temp_dir, "test-run-006")
        renames = [_make_validated("a.txt", "new-a.txt", temp_dir)]
        manifest.create(renames)

        assert manifest.path.exists()
        manifest.cleanup()
        assert not manifest.path.exists()


class TestManifestPersistence:
    def test_flush_writes_valid_json(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        manifest = Manifest(temp_dir, "test-run-007")
        renames = [_make_validated("a.txt", "new-a.txt", temp_dir)]
        manifest.create(renames)

        # Read back and verify valid JSON
        with open(manifest.path) as f:
            data = json.load(f)

        assert data["run_id"] == "test-run-007"
        assert data["status"] == "in_progress"
        assert len(data["renames"]) == 1

    def test_load_existing(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        manifest = Manifest(temp_dir, "test-run-008")
        renames = [_make_validated("a.txt", "new-a.txt", temp_dir)]
        manifest.create(renames)
        manifest.record_success(0)

        # Load from disk
        loaded = Manifest.load_existing(temp_dir)
        assert loaded is not None
        assert loaded.run_id == "test-run-008"
        assert loaded.is_complete

    def test_load_nonexistent_returns_none(self, temp_dir):
        loaded = Manifest.load_existing(temp_dir)
        assert loaded is None


class TestManifestProperties:
    def test_completed_renames(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        (temp_dir / "b.txt").write_text("world")

        manifest = Manifest(temp_dir, "test-run-009")
        renames = [
            _make_validated("a.txt", "new-a.txt", temp_dir),
            _make_validated("b.txt", "new-b.txt", temp_dir),
        ]
        manifest.create(renames)
        manifest.record_success(0)

        assert len(manifest.completed_renames) == 1
        assert len(manifest.pending_renames) == 1

    def test_failed_renames(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        manifest = Manifest(temp_dir, "test-run-010")
        renames = [_make_validated("a.txt", "new-a.txt", temp_dir)]
        manifest.create(renames)
        manifest.record_failure(0, "error")

        assert len(manifest.failed_renames) == 1


class TestManifestAtomicWrite:
    def test_no_partial_writes(self, temp_dir):
        """Verify that the manifest file is always complete JSON."""
        (temp_dir / "a.txt").write_text("content")
        manifest = Manifest(temp_dir, "atomic-test")
        renames = [_make_validated("a.txt", "new-a.txt", temp_dir)]
        manifest.create(renames)

        # Multiple rapid updates
        for i in range(10):
            manifest.record_intent(0)
            manifest.record_success(0)

        # File should always be valid JSON
        with open(manifest.path) as f:
            data = json.load(f)
        assert data["run_id"] == "atomic-test"
