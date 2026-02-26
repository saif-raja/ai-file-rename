"""
Context builder for ai-file-rename.

Enriches files with folder hierarchy context and groups them by parent folder.
This stage sits between metadata extraction and content analysis.
"""

from pathlib import Path

from ai_file_rename.models import EnrichedFile, FolderContext


def _build_breadcrumb(folder_path: Path, root_path: Path) -> str:
    """Build a human-readable breadcrumb trail from root to folder."""
    try:
        relative = folder_path.relative_to(root_path)
    except ValueError:
        return folder_path.name

    parts = list(relative.parts)
    if not parts:
        return root_path.name

    return " > ".join([root_path.name] + list(parts))


def _calculate_depth(folder_path: Path, root_path: Path) -> int:
    """Calculate nesting depth from root."""
    try:
        relative = folder_path.relative_to(root_path)
        return len(relative.parts)
    except ValueError:
        return 0


def build_context(
    files: list[EnrichedFile],
    target_root: Path,
) -> dict[Path, FolderContext]:
    """
    Group files by parent folder and build context for each group.

    Each FolderContext includes:
    - The folder's breadcrumb trail (hierarchy from root)
    - All files in the folder
    - Names of ALL sibling files (for the naming engine to see the full picture)
    - File count and depth information

    Args:
        files: List of enriched files from preprocessing.
        target_root: The root directory of the scan.

    Returns:
        Dict mapping folder paths to FolderContext objects.
    """
    # Only resolve if the path actually exists, to support synthetic test paths
    if target_root.exists():
        target_root = target_root.resolve()

    # Group files by parent folder
    folder_groups: dict[Path, list[EnrichedFile]] = {}

    for enriched_file in files:
        parent = enriched_file.entry.parent_folder
        if parent not in folder_groups:
            folder_groups[parent] = []
        folder_groups[parent].append(enriched_file)

    # Build context for each folder
    contexts: dict[Path, FolderContext] = {}

    for folder_path, folder_files in folder_groups.items():
        # Collect ALL file names in this folder (for sibling awareness)
        sibling_names = [f.entry.name for f in folder_files]

        # Also include files that exist in the folder but aren't being processed
        try:
            actual_files = [
                item.name
                for item in folder_path.iterdir()
                if item.is_file()
            ]
            # Merge: use actual files as the complete sibling list
            sibling_names = sorted(set(actual_files))
        except (OSError, PermissionError):
            sibling_names = sorted(set(sibling_names))

        breadcrumb = _build_breadcrumb(folder_path, target_root)
        depth = _calculate_depth(folder_path, target_root)

        contexts[folder_path] = FolderContext(
            folder_path=folder_path,
            folder_name=folder_path.name,
            breadcrumb=breadcrumb,
            depth=depth,
            files=folder_files,
            sibling_names=sibling_names,
            file_count=len(folder_files),
        )

    return contexts
