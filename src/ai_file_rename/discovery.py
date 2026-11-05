"""
File system scanner for ai-file-rename.

Walks the target directory, classifies every file, detects symlinks,
and builds the complete inventory for the pipeline.
"""

import fnmatch
import mimetypes
import os
from pathlib import Path
from typing import Optional

from ai_file_rename.config import Config
from ai_file_rename.constants import FORMAT_CATEGORIES, MIME_TYPE_MAP
from ai_file_rename.context import _build_breadcrumb, _calculate_depth
from ai_file_rename.models import (
    DiscoveryResult,
    FileCategory,
    FileEntry,
    FolderEntry,
    ImpactSummary,
    SymlinkEntry,
)


def _classify_file(extension: str) -> FileCategory:
    """Classify a file by its extension."""
    ext = extension.lower().lstrip(".")
    category_str = FORMAT_CATEGORIES.get(ext)
    if category_str is None:
        return FileCategory.UNSUPPORTED
    try:
        return FileCategory(category_str)
    except ValueError:
        return FileCategory.UNSUPPORTED


def _detect_mime_type(file_path: Path, extension: str) -> Optional[str]:
    """Detect MIME type from extension or magic bytes."""
    ext = extension.lower().lstrip(".")

    # Check our known map first
    if ext in MIME_TYPE_MAP:
        return MIME_TYPE_MAP[ext]

    # Fall back to Python's mimetypes module
    mime, _ = mimetypes.guess_type(str(file_path))
    return mime


def _is_excluded(path: Path, exclude_patterns: list[str]) -> bool:
    """Check if a path matches any exclude pattern."""
    name = path.name
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _is_included(path: Path, include_patterns: list[str]) -> bool:
    """Check if a path matches at least one include pattern.

    Returns True if there are no include patterns (i.e. everything is included
    by default) or if the file name matches any of the given patterns.
    """
    if not include_patterns:
        return True
    name = path.name
    for pattern in include_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def build_symlink_map(
    target_dir: Path, recursive: bool
) -> dict[str, list[SymlinkEntry]]:
    """
    Scan for all symlinks and build a reverse map.

    Maps resolved_target_path -> [symlinks pointing to it].
    This tells us, for any file we're about to rename,
    which symlinks will break and need updating.
    """
    symlink_map: dict[str, list[SymlinkEntry]] = {}

    items = target_dir.rglob("*") if recursive else target_dir.iterdir()

    for item in items:
        if item.is_symlink():
            try:
                target = item.resolve()
                raw_target = os.readlink(str(item))
                is_relative = not Path(raw_target).is_absolute()

                entry = SymlinkEntry(
                    symlink_path=item,
                    target_path=target,
                    is_relative=is_relative,
                )

                key = str(target)
                if key not in symlink_map:
                    symlink_map[key] = []
                symlink_map[key].append(entry)
            except (OSError, ValueError):
                # Broken symlink or permission issue: skip
                continue

    return symlink_map


def _estimate_api_calls(file_count: int) -> int:
    """Estimate number of API calls needed."""
    # Content analysis: ~1 call per 5 files (batched)
    analysis_calls = max(1, file_count // 5)
    # Naming: 1 call per folder (estimate 1 folder per 20 files)
    naming_calls = max(1, file_count // 20)
    return analysis_calls + naming_calls


def _estimate_cost(api_calls: int, model: str = "gemini-2.5-flash") -> float:
    """Rough cost estimate based on API calls."""
    # Very rough: ~5000 tokens per call, mostly input
    from ai_file_rename.constants import COST_PER_TOKEN

    costs = COST_PER_TOKEN.get(model, COST_PER_TOKEN.get("gemini-2.5-flash", {}))
    input_cost = costs.get("input", 0.0)
    output_cost = costs.get("output", 0.0)

    avg_input_tokens = 5000
    avg_output_tokens = 500

    per_call = (avg_input_tokens * input_cost) + (avg_output_tokens * output_cost)
    return round(api_calls * per_call, 2)


def discover(
    target_dir: Path,
    recursive: bool,
    config: Config,
) -> DiscoveryResult:
    """
    Scan target directory and return complete inventory.

    Args:
        target_dir: The directory to scan.
        recursive: Whether to recurse into subdirectories.
        config: Resolved configuration.

    Returns:
        DiscoveryResult containing files, folders, symlink map, and impact summary.

    Raises:
        FileNotFoundError: If target_dir does not exist.
        NotADirectoryError: If target_dir is not a directory.
        PermissionError: If target_dir is not readable.
    """
    target_dir = target_dir.resolve()

    if not target_dir.exists():
        raise FileNotFoundError(f"Target directory not found: {target_dir}")
    if not target_dir.is_dir():
        raise NotADirectoryError(f"Not a directory: {target_dir}")

    # Collect all items
    if recursive:
        all_items = list(target_dir.rglob("*"))
    else:
        all_items = list(target_dir.iterdir())

    # Build symlink map first
    symlink_map = build_symlink_map(target_dir, recursive)

    files: list[FileEntry] = []
    folders_dict: dict[Path, list[FileEntry]] = {}
    file_type_breakdown: dict[str, int] = {}
    warnings: list[str] = []

    symlinks_found = 0
    symlink_targets_in_scope = set()

    for item in all_items:
        # Skip directories themselves (we track them via files)
        if item.is_dir() and not item.is_symlink():
            continue

        # Skip excluded items
        if _is_excluded(item, config.exclude_patterns):
            continue

        # Skip items not matching include patterns (if any are set)
        if not _is_included(item, config.include_patterns):
            continue

        # Handle symlinks
        is_symlink = item.is_symlink()
        symlink_target = None

        if is_symlink:
            symlinks_found += 1
            try:
                symlink_target = item.resolve()
            except (OSError, ValueError):
                symlink_target = None

        # Skip if not a file (or symlink to file)
        if not item.is_file():
            continue

        # Get file info
        try:
            stat = item.stat()
            size = stat.st_size
        except (OSError, PermissionError):
            warnings.append(f"Cannot access: {item}")
            continue

        extension = item.suffix.lstrip(".").lower()
        category = _classify_file(extension)
        mime_type = _detect_mime_type(item, extension)

        # Track file type breakdown
        ext_key = extension if extension else "(no extension)"
        file_type_breakdown[ext_key] = file_type_breakdown.get(ext_key, 0) + 1

        # Determine skip reason
        skip_reason = None
        if category == FileCategory.UNSUPPORTED:
            skip_reason = f"Unsupported format: .{extension}"
        elif size > 2 * 1024**3:  # 2 GB
            skip_reason = "File exceeds 2 GB limit"
            category = FileCategory.UNSUPPORTED

        entry = FileEntry(
            path=item.resolve() if not is_symlink else item,
            name=item.name,
            stem=item.stem,
            extension=extension,
            mime_type=mime_type,
            size_bytes=size,
            is_symlink=is_symlink,
            symlink_target=symlink_target,
            category=category,
            parent_folder=item.parent.resolve(),
            skip_reason=skip_reason,
        )

        files.append(entry)

        # Track which folder this file belongs to
        parent = item.parent.resolve()
        if parent not in folders_dict:
            folders_dict[parent] = []
        folders_dict[parent].append(entry)

        # Track symlink targets
        key = str(item.resolve())
        if key in symlink_map:
            symlink_targets_in_scope.add(key)

    # Safety limit
    if len(files) > config.max_files:
        warnings.append(
            f"Found {len(files)} files, exceeding limit of {config.max_files}. "
            f"Only the first {config.max_files} will be processed."
        )
        files = files[: config.max_files]

    # Build folder entries
    folders: list[FolderEntry] = []
    deepest = 0

    for folder_path, folder_files in folders_dict.items():
        depth = _calculate_depth(folder_path, target_dir)
        deepest = max(deepest, depth)

        processable_files = [
            f for f in folder_files if f.category != FileCategory.UNSUPPORTED
        ]

        folders.append(
            FolderEntry(
                path=folder_path,
                name=folder_path.name,
                breadcrumb=_build_breadcrumb(folder_path, target_dir),
                depth=depth,
                file_count=len(processable_files),
                files=processable_files,
            )
        )

    # Sort folders by path for consistent ordering
    folders.sort(key=lambda f: str(f.path))

    # Count supported vs unsupported
    supported = sum(
        1 for f in files if f.category != FileCategory.UNSUPPORTED and not f.skip_reason
    )
    unsupported = len(files) - supported

    # Symlink warnings
    if symlinks_found > 0:
        warnings.append(
            f"Found {symlinks_found} symlink(s). Symlinks pointing to files "
            "from OUTSIDE the target directory will NOT be detected or updated."
        )

    # Estimate API usage
    estimated_calls = _estimate_api_calls(supported)
    estimated_cost = _estimate_cost(estimated_calls, config.model)

    impact = ImpactSummary(
        target_directory=target_dir,
        recursive=recursive,
        total_files=len(files),
        supported_files=supported,
        unsupported_files=unsupported,
        symlinks_found=symlinks_found,
        symlink_targets_in_scope=len(symlink_targets_in_scope),
        folders_affected=len(folders),
        deepest_nesting=deepest,
        estimated_api_calls=estimated_calls,
        estimated_cost_usd=estimated_cost,
        file_type_breakdown=file_type_breakdown,
        warnings=warnings,
    )

    return DiscoveryResult(
        files=files,
        folders=folders,
        symlink_map=symlink_map,
        impact=impact,
    )
