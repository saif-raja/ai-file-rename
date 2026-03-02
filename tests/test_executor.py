"""Tests for ai_file_rename.executor — safe rename execution and undo."""

import errno
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_file_rename.config import Config
from ai_file_rename.executor import (
    _is_locked_file_error,
    _is_network_drive,
    execute_renames,
    undo_renames,
    update_symlinks_for_rename,
)
from ai_file_rename.models import ProposedRename, SymlinkEntry, ValidatedRename


def _make_validated(current: str, proposed: str, parent: Path) -> ValidatedRename:
    """Helper to create a ValidatedRename."""
    return ValidatedRename(
        original=ProposedRename(
            current_name=current,
            proposed_name=proposed,
            current_path=parent / current,
            proposed_path=parent / proposed,
            reasoning="test rename",
            confidence=0.9,
        ),
        final_name=proposed,
    )


class TestExecuteRenames:
    def test_basic_rename(self, temp_dir):
        """Test renaming a single file."""
        (temp_dir / "old-name.txt").write_text("hello world")

        renames = [_make_validated("old-name.txt", "new-name.txt", temp_dir)]
        config = Config(gemini_api_key="test")

        result = execute_renames(renames, temp_dir, "test-001", config)

        assert result.renamed == 1
        assert result.failed == 0
        assert (temp_dir / "new-name.txt").exists()
        assert not (temp_dir / "old-name.txt").exists()
        assert (temp_dir / "new-name.txt").read_text() == "hello world"

    def test_multiple_renames(self, temp_dir):
        """Test renaming multiple files."""
        (temp_dir / "a.txt").write_text("content a")
        (temp_dir / "b.txt").write_text("content b")
        (temp_dir / "c.txt").write_text("content c")

        renames = [
            _make_validated("a.txt", "alpha.txt", temp_dir),
            _make_validated("b.txt", "beta.txt", temp_dir),
            _make_validated("c.txt", "gamma.txt", temp_dir),
        ]
        config = Config(gemini_api_key="test")

        result = execute_renames(renames, temp_dir, "test-002", config)

        assert result.renamed == 3
        assert result.failed == 0
        assert (temp_dir / "alpha.txt").read_text() == "content a"
        assert (temp_dir / "beta.txt").read_text() == "content b"
        assert (temp_dir / "gamma.txt").read_text() == "content c"

    def test_skip_unchanged(self, temp_dir):
        """Test that unchanged files are skipped."""
        (temp_dir / "same.txt").write_text("keep me")

        rename = ValidatedRename(
            original=ProposedRename(
                current_name="same.txt",
                proposed_name="same.txt",
                current_path=temp_dir / "same.txt",
                proposed_path=temp_dir / "same.txt",
                reasoning="already good",
                confidence=1.0,
                is_unchanged=True,
            ),
            final_name="same.txt",
        )
        config = Config(gemini_api_key="test")

        result = execute_renames([rename], temp_dir, "test-003", config)

        assert result.skipped == 1
        assert result.renamed == 0
        assert (temp_dir / "same.txt").exists()

    def test_halt_on_missing_source(self, temp_dir):
        """Test that execution halts when source file is missing."""
        # Don't create the file — it's missing
        renames = [_make_validated("nonexistent.txt", "new.txt", temp_dir)]
        config = Config(gemini_api_key="test")

        result = execute_renames(renames, temp_dir, "test-004", config)

        assert result.failed == 1
        assert result.renamed == 0

    def test_halt_on_target_exists(self, temp_dir):
        """Test that execution halts when target already exists."""
        (temp_dir / "source.txt").write_text("source")
        (temp_dir / "target.txt").write_text("occupying target")

        renames = [_make_validated("source.txt", "target.txt", temp_dir)]
        config = Config(gemini_api_key="test")

        result = execute_renames(renames, temp_dir, "test-005", config)

        assert result.failed == 1
        # Source should be untouched
        assert (temp_dir / "source.txt").exists()

    def test_halt_stops_remaining(self, temp_dir):
        """Test that failure on one file halts the entire batch."""
        (temp_dir / "a.txt").write_text("a")
        # b.txt doesn't exist — will cause failure
        (temp_dir / "c.txt").write_text("c")

        renames = [
            _make_validated("a.txt", "alpha.txt", temp_dir),
            _make_validated("b.txt", "beta.txt", temp_dir),  # Will fail
            _make_validated("c.txt", "gamma.txt", temp_dir),
        ]
        config = Config(gemini_api_key="test")

        result = execute_renames(renames, temp_dir, "test-006", config)

        assert result.renamed == 1  # Only a.txt succeeded
        assert result.failed == 1   # b.txt failed
        # c.txt should NOT have been renamed (batch halted)
        assert (temp_dir / "c.txt").exists()

    def test_manifest_cleanup_on_success(self, temp_dir):
        """Test that manifest is cleaned up on full success."""
        (temp_dir / "a.txt").write_text("hello")

        renames = [_make_validated("a.txt", "new-a.txt", temp_dir)]
        config = Config(gemini_api_key="test")

        result = execute_renames(renames, temp_dir, "test-007", config)

        assert result.failed == 0
        # Manifest should be cleaned up
        assert not (temp_dir / ".ai-rename-manifest.json").exists()

    def test_manifest_preserved_on_failure(self, temp_dir):
        """Test that manifest persists when there are failures."""
        # Missing source will cause failure
        renames = [_make_validated("missing.txt", "new.txt", temp_dir)]
        config = Config(gemini_api_key="test")

        result = execute_renames(renames, temp_dir, "test-008", config)

        assert result.failed == 1
        # Manifest should still exist
        assert (temp_dir / ".ai-rename-manifest.json").exists()

    def test_file_size_preserved(self, temp_dir):
        """Test that file size is preserved after rename."""
        content = "x" * 1000
        (temp_dir / "original.txt").write_text(content)
        original_size = (temp_dir / "original.txt").stat().st_size

        renames = [_make_validated("original.txt", "renamed.txt", temp_dir)]
        config = Config(gemini_api_key="test")

        execute_renames(renames, temp_dir, "test-009", config)

        assert (temp_dir / "renamed.txt").stat().st_size == original_size


class TestUndoRenames:
    def test_undo_single_rename(self, temp_dir):
        """Test undoing a single rename."""
        (temp_dir / "original.txt").write_text("content")

        renames = [_make_validated("original.txt", "renamed.txt", temp_dir)]
        config = Config(gemini_api_key="test")

        # Execute
        execute_renames(renames, temp_dir, "test-undo-001", config)

        # Re-create manifest for undo (execute cleans it up on success)
        from ai_file_rename.manifest import Manifest
        manifest = Manifest(temp_dir, "test-undo-001")
        manifest.create(renames)
        manifest.record_success(0)

        # Undo
        result = undo_renames(temp_dir)

        assert result.renamed == 1
        assert (temp_dir / "original.txt").exists()
        assert not (temp_dir / "renamed.txt").exists()

    def test_undo_no_manifest_raises(self, temp_dir):
        """Test that undo raises when no manifest exists."""
        with pytest.raises(FileNotFoundError):
            undo_renames(temp_dir)


class TestUpdateSymlinks:
    def test_update_relative_symlink(self, temp_dir):
        """Test updating a relative symlink after rename."""
        real_file = temp_dir / "old-name.txt"
        real_file.write_text("real content")
        new_file = temp_dir / "new-name.txt"

        # Create a symlink
        link = temp_dir / "link.txt"
        os.symlink("old-name.txt", str(link))

        # Simulate rename
        os.rename(str(real_file), str(new_file))

        # Update symlink
        entries = [
            SymlinkEntry(
                symlink_path=link,
                target_path=real_file,
                is_relative=True,
            )
        ]
        results = update_symlinks_for_rename(real_file, new_file, entries)

        assert len(results) == 1
        assert results[0][1] is True  # success
        # Symlink should now point to new name
        assert os.readlink(str(link)) == "new-name.txt"

    def test_update_absolute_symlink(self, temp_dir):
        """Test updating an absolute symlink after rename."""
        real_file = temp_dir / "old-name.txt"
        real_file.write_text("real content")
        new_file = temp_dir / "new-name.txt"

        # Create absolute symlink
        link = temp_dir / "abs-link.txt"
        os.symlink(str(real_file), str(link))

        # Simulate rename
        os.rename(str(real_file), str(new_file))

        entries = [
            SymlinkEntry(
                symlink_path=link,
                target_path=real_file,
                is_relative=False,
            )
        ]
        results = update_symlinks_for_rename(real_file, new_file, entries)

        assert results[0][1] is True
        assert str(new_file) in os.readlink(str(link))


# --- ISSUE-20: PID-qualified temp symlink path ---


class TestSymlinkTempPathPid:
    """Tests for ISSUE-20: temp symlink paths should be PID-qualified."""

    def test_temp_symlink_contains_pid(self, temp_dir):
        """update_symlinks_for_rename uses PID-qualified temp path to avoid collisions."""
        real_file = temp_dir / "old-name.txt"
        real_file.write_text("real content")
        new_file = temp_dir / "new-name.txt"

        # Create a symlink
        link = temp_dir / "link.txt"
        os.symlink("old-name.txt", str(link))

        # Simulate rename
        os.rename(str(real_file), str(new_file))

        entries = [
            SymlinkEntry(
                symlink_path=link,
                target_path=real_file,
                is_relative=True,
            )
        ]

        # Patch os.symlink to capture the temp path used
        original_symlink = os.symlink
        temp_paths_used = []

        def tracking_symlink(src, dst, *args, **kwargs):
            if "ai-rename-tmp" in str(dst):
                temp_paths_used.append(dst)
            return original_symlink(src, dst, *args, **kwargs)

        with patch("os.symlink", side_effect=tracking_symlink):
            update_symlinks_for_rename(real_file, new_file, entries)

        # Verify PID was included in temp path
        pid = str(os.getpid())
        assert any(pid in str(p) for p in temp_paths_used), (
            f"Expected PID {pid} in temp symlink paths: {temp_paths_used}"
        )

    def test_no_stale_temp_symlink_after_update(self, temp_dir):
        """No .ai-rename-tmp files should remain after successful symlink update."""
        real_file = temp_dir / "old.txt"
        real_file.write_text("content")
        new_file = temp_dir / "new.txt"

        link = temp_dir / "mylink.txt"
        os.symlink("old.txt", str(link))
        os.rename(str(real_file), str(new_file))

        entries = [
            SymlinkEntry(
                symlink_path=link,
                target_path=real_file,
                is_relative=True,
            )
        ]

        update_symlinks_for_rename(real_file, new_file, entries)

        # No temp files should remain
        remaining = list(temp_dir.glob("*.ai-rename-tmp*"))
        assert len(remaining) == 0, f"Stale temp files remain: {remaining}"


class TestLockedFileHandling:
    def test_permission_error_is_locked(self):
        """PermissionError is treated as a locked-file error."""
        err = PermissionError(errno.EACCES, "Permission denied")
        assert _is_locked_file_error(err) is True

    def test_eacces_oserror_is_locked(self):
        """OSError with EACCES errno is treated as a locked-file error."""
        err = OSError(errno.EACCES, "Access denied")
        assert _is_locked_file_error(err) is True

    def test_generic_oserror_is_not_locked(self):
        """Generic OSError (e.g. ENOENT) is NOT treated as locked."""
        err = OSError(errno.ENOENT, "No such file")
        assert _is_locked_file_error(err) is False

    def test_locked_file_skipped_not_halted(self, temp_dir):
        """Locked files are skipped and remaining renames continue."""
        (temp_dir / "a.txt").write_text("a")
        (temp_dir / "b.txt").write_text("b")
        (temp_dir / "c.txt").write_text("c")

        renames = [
            _make_validated("a.txt", "alpha.txt", temp_dir),
            _make_validated("b.txt", "beta.txt", temp_dir),
            _make_validated("c.txt", "gamma.txt", temp_dir),
        ]
        config = Config(gemini_api_key="test")

        # Make b.txt's rename raise PermissionError (locked file)
        original_rename = os.rename

        def mock_rename(src, dst):
            if "b.txt" in src:
                raise PermissionError(errno.EACCES, "File locked", src)
            return original_rename(src, dst)

        with patch("ai_file_rename.executor.os.rename", side_effect=mock_rename):
            result = execute_renames(renames, temp_dir, "test-lock", config)

        # b.txt should be skipped (not failed), a and c should succeed
        assert result.renamed == 2
        assert result.skipped == 1  # b.txt skipped due to lock
        assert result.failed == 0
        assert (temp_dir / "alpha.txt").exists()
        assert (temp_dir / "b.txt").exists()  # Unchanged
        assert (temp_dir / "gamma.txt").exists()


class TestNetworkDriveDetection:
    def test_same_device_is_not_network(self, temp_dir):
        """Files on the same device as the root are not network drives."""
        (temp_dir / "file.txt").write_text("hello")
        assert _is_network_drive(temp_dir / "file.txt", temp_dir) is False

    def test_different_device_is_network(self, temp_dir):
        """Files on a different st_dev are detected as network drive."""
        (temp_dir / "file.txt").write_text("hello")

        # Mock st_dev to differ
        real_stat = Path.stat

        def mock_stat(self):
            result = real_stat(self)
            if "file.txt" in str(self):
                # Return a fake stat with different st_dev
                import types
                fake = types.SimpleNamespace(**{
                    k: getattr(result, k) for k in dir(result)
                    if not k.startswith("_")
                })
                fake.st_dev = result.st_dev + 999
                return fake
            return result

        with patch.object(Path, "stat", mock_stat):
            assert _is_network_drive(temp_dir / "file.txt", temp_dir) is True

    def test_network_drive_warning_surfaces_in_result(self, temp_dir):
        """Network drive detection produces a warning in ExecutionResult."""
        (temp_dir / "file.txt").write_text("hello")

        renames = [_make_validated("file.txt", "renamed.txt", temp_dir)]
        config = Config(gemini_api_key="test")

        # Mock _is_network_drive to return True
        with patch("ai_file_rename.executor._is_network_drive", return_value=True):
            result = execute_renames(renames, temp_dir, "test-net", config)

        assert result.renamed == 1
        assert len(result.warnings) == 1
        assert "network" in result.warnings[0].lower() or "drive" in result.warnings[0].lower()
