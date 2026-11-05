"""
Safe rename executor for ai-file-rename.

Executes renames atomically with manifest tracking.
Follows the protocol: record intent -> rename -> verify -> record success.
"""

import errno
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from ai_file_rename.config import Config
from ai_file_rename.manifest import Manifest
from ai_file_rename.models import (
    ExecutionResult,
    RenameResult,
    SymlinkEntry,
    ValidatedRename,
)


def _is_locked_file_error(err: OSError) -> bool:
    """Check if an OSError indicates a file is locked by another process.

    On Windows this manifests as PermissionError or EACCES.
    On POSIX it can be EACCES or EAGAIN (advisory locks).
    """
    if isinstance(err, PermissionError):
        return True
    return err.errno in (errno.EACCES, getattr(errno, "EAGAIN", -1))


def _is_network_drive(file_path: Path, root_path: Path) -> bool:
    """Check if a file resides on a different device than the root directory.

    A different st_dev value implies the file is on a mount point or
    network drive, where os.rename() atomicity is not guaranteed.
    """
    try:
        file_dev = file_path.stat().st_dev
        root_dev = root_path.stat().st_dev
        return file_dev != root_dev
    except OSError:
        return False


def _verify_rename(old_path: Path, new_path: Path, expected_size: int) -> Optional[str]:
    """
    Verify that a rename succeeded.

    Returns None on success, or an error message on failure.
    """
    if old_path.exists():
        return f"Old path still exists after rename: {old_path}"

    if not new_path.exists():
        return f"New path not found after rename: {new_path}"

    actual_size = new_path.stat().st_size
    if actual_size != expected_size:
        return (
            f"File size mismatch after rename: "
            f"expected {expected_size}, got {actual_size}"
        )

    return None


def update_symlinks_for_rename(
    old_path: Path,
    new_path: Path,
    symlink_entries: list[SymlinkEntry],
) -> list[tuple[Path, bool]]:
    """
    Update all symlinks that pointed to old_path to point to new_path.

    Uses atomic symlink update: create temp link, then os.replace().

    Returns:
        List of (symlink_path, success) tuples.
    """
    results = []
    new_name = new_path.name

    for entry in symlink_entries:
        symlink = entry.symlink_path

        if not symlink.is_symlink():
            results.append((symlink, False))
            continue

        try:
            if entry.is_relative:
                new_target = new_name
            else:
                new_target = str(new_path)

            # Atomic symlink update
            temp_link = symlink.with_suffix(f".ai-rename-tmp-{os.getpid()}")
            os.symlink(new_target, str(temp_link))
            os.replace(str(temp_link), str(symlink))

            results.append((symlink, True))
        except OSError:
            results.append((symlink, False))

    return results


def execute_renames(
    renames: list[ValidatedRename],
    manifest_dir: Path,
    run_id: str,
    config: Config,
    symlink_map: Optional[dict[str, list[SymlinkEntry]]] = None,
) -> ExecutionResult:
    """
    Execute all validated renames with full safety guarantees.

    Protocol per file:
    1. Record intent in manifest
    2. Execute os.rename()
    3. Verify rename succeeded
    4. Update symlinks pointing to this file
    5. Record success in manifest

    On any failure: halt immediately, preserve manifest.
    Exception: locked files (PermissionError/EACCES) are skipped and
    processing continues with the next file.

    Args:
        renames: List of validated renames to execute.
        manifest_dir: Directory for the manifest file.
        run_id: Unique run identifier.
        config: Resolved configuration.
        symlink_map: Optional mapping of file paths to incoming symlinks.

    Returns:
        ExecutionResult with counts and individual results.
    """
    if symlink_map is None:
        symlink_map = {}

    started_at = datetime.now()
    manifest = Manifest(manifest_dir, run_id)
    manifest.create(renames)

    results: list[RenameResult] = []
    renamed_count = 0
    skipped_count = 0
    failed_count = 0
    total_symlinks_updated = 0
    network_drive_warned = False
    execution_warnings: list[str] = []

    for i, validated in enumerate(renames):
        rename = validated.original
        final_name = validated.final_name

        # Skip unchanged files
        if rename.is_unchanged or final_name == rename.current_name:
            manifest.record_success(i)
            skipped_count += 1
            results.append(
                RenameResult(
                    old_path=rename.current_path,
                    new_path=rename.current_path,
                    status="skipped",
                )
            )
            continue

        old_path = rename.current_path
        new_path = old_path.parent / final_name

        # Pre-flight checks
        if not old_path.exists():
            error = f"Source file missing: {old_path}"
            manifest.record_failure(i, error)
            failed_count += 1
            results.append(
                RenameResult(
                    old_path=old_path,
                    new_path=new_path,
                    status="failed",
                    error=error,
                )
            )
            break  # Halt on first failure

        if new_path.exists():
            error = f"Target already exists: {new_path}"
            manifest.record_failure(i, error)
            failed_count += 1
            results.append(
                RenameResult(
                    old_path=old_path,
                    new_path=new_path,
                    status="failed",
                    error=error,
                )
            )
            break  # Halt on first failure

        # Network drive detection: warn once if file is on a different device
        if not network_drive_warned and _is_network_drive(old_path, manifest_dir):
            network_drive_warned = True
            execution_warnings.append(
                f"Target appears to be on a network/external drive "
                f"(device differs from {manifest_dir}). "
                f"os.rename() atomicity is not guaranteed."
            )

        expected_size = old_path.stat().st_size

        # Step 1: Record intent
        manifest.record_intent(i)

        # Step 2: Execute rename
        try:
            os.rename(str(old_path), str(new_path))
        except OSError as e:
            if _is_locked_file_error(e):
                # Locked file: skip and continue (PRD exception to halt-on-failure).
                # Manifest records this as "failed" (mechanically correct: the
                # rename was attempted and couldn't proceed). ExecutionResult
                # counts it as "skipped" (user-facing: the batch continued).
                # On resume, manifest.pending_renames excludes "failed" entries
                # so this file won't be retried automatically.
                error = f"File locked by another process, skipping: {e}"
                manifest.record_failure(i, error)
                skipped_count += 1
                results.append(
                    RenameResult(
                        old_path=old_path,
                        new_path=new_path,
                        status="skipped",
                        error=error,
                    )
                )
                continue
            error = f"Rename failed: {e}"
            manifest.record_failure(i, error)
            failed_count += 1
            results.append(
                RenameResult(
                    old_path=old_path,
                    new_path=new_path,
                    status="failed",
                    error=error,
                )
            )
            break  # Halt on first failure

        # Step 3: Verify
        verify_error = _verify_rename(old_path, new_path, expected_size)
        if verify_error:
            manifest.record_failure(i, verify_error)
            failed_count += 1
            results.append(
                RenameResult(
                    old_path=old_path,
                    new_path=new_path,
                    status="failed",
                    error=verify_error,
                )
            )
            break  # Halt on first failure

        # Step 4: Update symlinks
        symlinks_updated = 0
        key = str(old_path)
        if key in symlink_map:
            symlink_results = update_symlinks_for_rename(
                old_path, new_path, symlink_map[key]
            )
            symlinks_updated = sum(1 for _, ok in symlink_results if ok)
            total_symlinks_updated += symlinks_updated

        # Also update symlinks from the validated rename's plan
        for symlink_path, new_target in validated.symlink_updates:
            try:
                if Path(symlink_path).is_symlink():
                    temp_link = Path(symlink_path).with_suffix(f".ai-rename-tmp-{os.getpid()}")
                    os.symlink(new_target, str(temp_link))
                    os.replace(str(temp_link), str(symlink_path))
                    symlinks_updated += 1
                    total_symlinks_updated += 1
            except OSError:
                pass

        # Step 5: Record success
        manifest.record_success(i)
        renamed_count += 1
        results.append(
            RenameResult(
                old_path=old_path,
                new_path=new_path,
                status="completed",
                symlinks_updated=symlinks_updated,
            )
        )

    # Finalize
    completed_at = datetime.now()

    if failed_count == 0:
        manifest.mark_complete()
        manifest.cleanup()
    # If there were failures, the manifest remains for recovery

    return ExecutionResult(
        run_id=run_id,
        target_directory=manifest_dir,
        started_at=started_at,
        completed_at=completed_at,
        total_files=len(renames),
        renamed=renamed_count,
        skipped=skipped_count,
        failed=failed_count,
        symlinks_updated=total_symlinks_updated,
        results=results,
        warnings=execution_warnings,
    )


def undo_renames(manifest_path: Path) -> ExecutionResult:
    """
    Reverse all renames recorded in a manifest file.

    Processes in reverse order (last renamed file is un-renamed first).

    Args:
        manifest_path: Path to the directory containing the manifest.

    Returns:
        ExecutionResult describing the undo operation.
    """
    manifest = Manifest.load_existing(manifest_path)
    if manifest is None:
        raise FileNotFoundError(
            f"No manifest found in {manifest_path}. Nothing to undo."
        )

    started_at = datetime.now()
    results: list[RenameResult] = []
    renamed_count = 0
    failed_count = 0

    # Get completed renames in reverse order
    completed = manifest.completed_renames
    completed.reverse()

    for entry in completed:
        old_path = Path(entry["new_path"])  # Current name (was new_path)
        new_path = Path(entry["old_path"])  # Restore to original name

        if not old_path.exists():
            # Already undone or file moved
            results.append(
                RenameResult(
                    old_path=old_path,
                    new_path=new_path,
                    status="skipped",
                    error="File not found at renamed path",
                )
            )
            continue

        if new_path.exists():
            results.append(
                RenameResult(
                    old_path=old_path,
                    new_path=new_path,
                    status="failed",
                    error="Original name already occupied",
                )
            )
            failed_count += 1
            continue

        try:
            os.rename(str(old_path), str(new_path))
            renamed_count += 1
            results.append(
                RenameResult(
                    old_path=old_path,
                    new_path=new_path,
                    status="completed",
                )
            )
        except OSError as e:
            failed_count += 1
            results.append(
                RenameResult(
                    old_path=old_path,
                    new_path=new_path,
                    status="failed",
                    error=str(e),
                )
            )

    # Clean up manifest
    if failed_count == 0:
        manifest.cleanup()

    return ExecutionResult(
        run_id=f"undo-{manifest.run_id}",
        target_directory=manifest_path,
        started_at=started_at,
        completed_at=datetime.now(),
        total_files=len(completed),
        renamed=renamed_count,
        skipped=len(completed) - renamed_count - failed_count,
        failed=failed_count,
        symlinks_updated=0,
        results=results,
    )
