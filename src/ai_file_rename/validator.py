"""
Name validation and collision resolution for ai-file-rename.

Ensures all proposed names are valid, unique, and cross-platform safe.
This module is a pure function — no side effects, no I/O, no external deps.
"""

import re
import unicodedata
from pathlib import Path
from typing import Optional

from ai_file_rename.models import (
    ProposedRename,
    SymlinkEntry,
    ValidatedRename,
)

# Cross-platform forbidden characters (union of Windows + macOS + Linux)
FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows reserved device names
WINDOWS_RESERVED = frozenset({
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
})

MAX_NAME_LENGTH = 200


def sanitize_name(proposed_name: str) -> str:
    """
    Sanitize a proposed file stem to be cross-platform safe.

    This does NOT include the extension — only the stem is sanitized.

    Steps:
    1. Transliterate Unicode to ASCII
    2. Lowercase
    3. Replace forbidden characters with hyphens
    4. Replace spaces and underscores with hyphens
    5. Collapse multiple hyphens
    6. Strip leading/trailing hyphens and dots
    7. Check for reserved names
    8. Handle leading dots
    9. Handle empty result

    Args:
        proposed_name: The proposed file stem (without extension).

    Returns:
        A sanitized, cross-platform-safe file stem.
    """
    name = proposed_name.strip()

    # 1. Transliterate Unicode to ASCII
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    # 2. Lowercase
    name = name.lower()

    # 3. Replace forbidden characters with hyphens
    name = FORBIDDEN_CHARS.sub("-", name)

    # 4. Replace spaces and underscores with hyphens
    name = re.sub(r"[\s_]+", "-", name)

    # 5. Collapse multiple hyphens
    name = re.sub(r"-+", "-", name)

    # 6. Strip leading/trailing hyphens and dots
    name = name.strip("-.")

    # 7. Check for reserved names
    stem_only = name.split(".")[0] if "." in name else name
    if stem_only in WINDOWS_RESERVED:
        name = f"file-{name}"

    # 8. Handle leading dots (would make file hidden on Unix)
    if name.startswith("."):
        name = f"_{name}"

    # 9. Handle empty result
    if not name:
        name = "unnamed-file"

    return name


def truncate_name(name: str, extension: str, max_length: int = MAX_NAME_LENGTH) -> str:
    """
    Truncate a file stem to fit within the max name length.

    Truncates at a word boundary (last hyphen) when possible.

    Args:
        name: The sanitized file stem.
        extension: The file extension (without leading dot).
        max_length: Maximum total file name length (stem + dot + extension).

    Returns:
        Truncated stem that fits within limits.
    """
    # Account for the dot and extension
    max_stem = max_length - len(extension) - 1

    if len(name) <= max_stem:
        return name

    truncated = name[:max_stem]

    # Try to truncate at a word boundary
    last_hyphen = truncated.rfind("-")
    if last_hyphen > max_stem // 2:
        name = truncated[:last_hyphen]
    else:
        name = truncated

    return name


def resolve_collisions(renames: list[ProposedRename]) -> list[ProposedRename]:
    """
    Resolve name collisions within a set of proposed renames.

    If two files would get the same name, append numeric suffixes
    starting at 2 (the first file keeps the clean name).

    Args:
        renames: List of proposed renames to check.

    Returns:
        Updated list with collisions resolved.
    """
    # Track proposed names (lowercased for case-insensitive comparison)
    name_counts: dict[str, int] = {}
    result = []

    for rename in renames:
        proposed_lower = rename.proposed_name.lower()

        if proposed_lower in name_counts:
            # Collision — append suffix
            count = name_counts[proposed_lower] + 1
            name_counts[proposed_lower] = count

            # Split into stem and extension
            path = Path(rename.proposed_name)
            stem = path.stem
            ext = path.suffix  # includes the dot

            new_name = f"{stem}-{count}{ext}"
            new_path = rename.current_path.parent / new_name

            result.append(
                ProposedRename(
                    current_name=rename.current_name,
                    proposed_name=new_name,
                    current_path=rename.current_path,
                    proposed_path=new_path,
                    reasoning=rename.reasoning,
                    confidence=rename.confidence,
                    is_unchanged=rename.is_unchanged,
                    has_incoming_symlinks=rename.has_incoming_symlinks,
                    incoming_symlinks=rename.incoming_symlinks,
                )
            )
        else:
            name_counts[proposed_lower] = 1
            result.append(rename)

    return result


def check_existing_collisions(
    renames: list[ProposedRename],
    existing_files: set[str],
    files_being_renamed: set[str],
) -> list[ProposedRename]:
    """
    Check proposed names against existing files that are NOT being renamed.

    Args:
        renames: Proposed renames to check.
        existing_files: All file names currently in the directory.
        files_being_renamed: Names of files that are part of this rename batch.

    Returns:
        Updated list with collisions against existing files resolved.
    """
    # Files that will remain unchanged
    immovable = {f.lower() for f in existing_files - files_being_renamed}

    result = []
    for rename in renames:
        proposed_lower = rename.proposed_name.lower()

        if proposed_lower in immovable:
            # Collision with an existing file not being renamed
            path = Path(rename.proposed_name)
            stem = path.stem
            ext = path.suffix
            counter = 2

            while f"{stem}-{counter}{ext}".lower() in immovable:
                counter += 1

            new_name = f"{stem}-{counter}{ext}"
            new_path = rename.current_path.parent / new_name

            result.append(
                ProposedRename(
                    current_name=rename.current_name,
                    proposed_name=new_name,
                    current_path=rename.current_path,
                    proposed_path=new_path,
                    reasoning=rename.reasoning,
                    confidence=rename.confidence,
                    is_unchanged=rename.is_unchanged,
                    has_incoming_symlinks=rename.has_incoming_symlinks,
                    incoming_symlinks=rename.incoming_symlinks,
                )
            )
        else:
            result.append(rename)

    return result


def plan_symlink_updates(
    rename: ProposedRename,
    symlink_map: dict[str, list[SymlinkEntry]],
) -> list[tuple[Path, str]]:
    """
    Determine which symlinks need updating when a file is renamed.

    Args:
        rename: The proposed rename.
        symlink_map: Mapping of resolved file paths to their incoming symlinks.

    Returns:
        List of (symlink_path, new_target_name) tuples.
    """
    key = str(rename.current_path)
    entries = symlink_map.get(key, [])

    updates = []
    new_name = rename.proposed_name

    for entry in entries:
        if entry.is_relative:
            updates.append((entry.symlink_path, new_name))
        else:
            new_target = str(rename.current_path.parent / new_name)
            updates.append((entry.symlink_path, new_target))

    return updates


def validate_renames(
    renames: list[ProposedRename],
    symlink_map: Optional[dict[str, list[SymlinkEntry]]] = None,
    existing_files: Optional[set[str]] = None,
    files_being_renamed: Optional[set[str]] = None,
) -> list[ValidatedRename]:
    """
    Validate and sanitize all proposed renames.

    Performs:
    1. Name sanitization (cross-platform safety)
    2. Length truncation
    3. Internal collision resolution
    4. External collision resolution (against existing files)
    5. Symlink update planning

    Args:
        renames: List of proposed renames from the naming engine.
        symlink_map: Mapping of file paths to incoming symlinks.
        existing_files: All file names in the target directory.
        files_being_renamed: Names of files being renamed in this batch.

    Returns:
        List of validated, ready-to-execute renames.
    """
    if symlink_map is None:
        symlink_map = {}
    if existing_files is None:
        existing_files = set()
    if files_being_renamed is None:
        files_being_renamed = {r.current_name for r in renames}

    validated = []

    # First pass: sanitize and truncate each name
    sanitized_renames = []
    for rename in renames:
        notes = []

        # Split proposed name into stem and extension
        proposed_path = Path(rename.proposed_name)
        extension = proposed_path.suffix.lstrip(".")
        stem = proposed_path.stem

        # Sanitize the stem
        clean_stem = sanitize_name(stem)
        if clean_stem != stem.lower():
            notes.append(f"Sanitized: '{stem}' -> '{clean_stem}'")

        # Truncate if needed
        truncated = truncate_name(clean_stem, extension)
        if truncated != clean_stem:
            notes.append(f"Truncated: '{clean_stem}' -> '{truncated}'")

        final_name = f"{truncated}.{extension}" if extension else truncated
        final_path = rename.current_path.parent / final_name

        sanitized_renames.append(
            ProposedRename(
                current_name=rename.current_name,
                proposed_name=final_name,
                current_path=rename.current_path,
                proposed_path=final_path,
                reasoning=rename.reasoning,
                confidence=rename.confidence,
                is_unchanged=(final_name == rename.current_name),
                has_incoming_symlinks=rename.has_incoming_symlinks,
                incoming_symlinks=rename.incoming_symlinks,
            )
        )

    # Second pass: resolve internal collisions
    resolved = resolve_collisions(sanitized_renames)

    # Third pass: resolve external collisions
    resolved = check_existing_collisions(resolved, existing_files, files_being_renamed)

    # Final pass: create ValidatedRename objects with symlink plans
    for i, rename in enumerate(resolved):
        notes = []

        # Check if sanitization changed the name
        original = renames[i]
        if rename.proposed_name != original.proposed_name:
            notes.append(
                f"Adjusted from '{original.proposed_name}' to '{rename.proposed_name}'"
            )

        # Detect collision resolution
        collision_resolved = rename.proposed_name != sanitize_and_build_name(
            original.proposed_name
        )

        # Plan symlink updates
        symlink_updates = plan_symlink_updates(rename, symlink_map)
        if symlink_updates:
            notes.append(f"{len(symlink_updates)} symlink(s) will be updated")

        validated.append(
            ValidatedRename(
                original=rename,
                final_name=rename.proposed_name,
                validation_notes=notes,
                collision_resolved=collision_resolved,
                symlink_updates=symlink_updates,
            )
        )

    return validated


def sanitize_and_build_name(proposed_name: str) -> str:
    """Helper: sanitize a full filename (stem + extension)."""
    p = Path(proposed_name)
    extension = p.suffix.lstrip(".")
    stem = p.stem
    clean = sanitize_name(stem)
    truncated = truncate_name(clean, extension)
    return f"{truncated}.{extension}" if extension else truncated


def is_well_named(filename: str) -> bool:
    """
    Heuristic check: is this file already descriptively named?

    Checks:
    1. Name length > 15 characters
    2. Contains multiple real words (3+ meaningful word-like tokens)
    3. Does not match common default patterns
    4. No repeated words (case-insensitive)
    5. No version/draft indicators (v1, _FINAL, _draft, _copy)
    6. No ALL_CAPS tokens (suggests sloppy or automated naming)
    7. Tokens must be semantically meaningful (not generic filler)

    Args:
        filename: The file name to check (with extension).

    Returns:
        True if the file appears to already be well-named.
    """
    import re as _re

    stem = Path(filename).stem

    # Too short to be descriptive
    if len(stem) < 15:
        return False

    # Check for default/bad name patterns
    default_patterns = [
        r"^IMG_\d",
        r"^DSC_?\d",
        r"^DSCN\d",
        r"^DCIM",
        r"^Screenshot",
        r"^Screen Shot",
        r"^Screen Recording",
        r"^download",
        r"^document",
        r"^Untitled",
        r"^Copy of",
        r"^[0-9a-f]{8,}$",  # Hex hash
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",  # UUID
        r"\(\d+\)$",  # Numbered duplicate
        r"^VID_\d",
        r"^Voice Memo",
        r"^Recording",
        r"^track\d",
    ]

    for pattern in default_patterns:
        if _re.search(pattern, stem, _re.IGNORECASE):
            return False

    # Check for version/draft indicators — these suggest naming noise
    version_patterns = [
        r"[-_\s]v\d+",               # v1, v2, etc.
        r"[-_\s](?:FINAL|final)",     # _FINAL, -final
        r"[-_\s](?:DRAFT|draft)",     # _DRAFT, -draft
        r"[-_\s](?:COPY|copy)",       # _COPY, -copy
        r"[-_\s](?:NEW|new|OLD|old)", # _NEW, _OLD
        r"[-_\s](?:TEMP|temp)",       # _TEMP, -temp
    ]
    for pattern in version_patterns:
        if _re.search(pattern, stem):
            return False

    # Tokenize by separators and check for real word-like tokens
    tokens = _re.split(r"[-_\s]+", stem)
    word_tokens = [t for t in tokens if len(t) >= 2 and t.isalpha()]

    # Check for repeated words (case-insensitive) — e.g. "final_v2_FINAL"
    lowered = [t.lower() for t in word_tokens]
    if len(lowered) != len(set(lowered)):
        return False

    # Check for ALL_CAPS tokens (more than 1 suggests sloppy naming)
    all_caps_count = sum(1 for t in word_tokens if t.isupper() and len(t) > 1)
    if all_caps_count > 1:
        return False

    # Filter out generic filler words that don't carry semantic meaning
    _FILLER_WORDS = frozenset({
        "file", "document", "copy", "new", "old", "temp", "test",
        "the", "and", "for", "with", "from", "this", "that",
    })
    meaningful_tokens = [t for t in word_tokens if t.lower() not in _FILLER_WORDS]

    # Needs at least 3 semantically meaningful tokens
    return len(meaningful_tokens) >= 3
