"""Data model layer for the AI file rename tool.

This is the foundation module that all other modules depend on. It defines
every data structure used throughout the pipeline: discovery, metadata
extraction, content analysis, rename proposal, validation, and execution.

All models use Pydantic v2 BaseModel for runtime validation and serialization.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "FileCategory",
    "FileEntry",
    "SymlinkEntry",
    "FolderEntry",
    "FileMetadata",
    "EnrichedFile",
    "FolderContext",
    "ContentSummary",
    "AnalyzedFile",
    "ProposedRename",
    "ValidatedRename",
    "RenameResult",
    "ExecutionResult",
    "ImpactSummary",
    "DiscoveryResult",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FileCategory(str, Enum):
    """Classification of a file's processability.

    DIRECTLY_PROCESSABLE - Gemini can ingest the file natively (e.g. PDF, images).
    CONVERTIBLE         - The file can be converted to a supported format first.
    TEXT_EXTRACTABLE    - Plain text or content can be extracted for analysis.
    UNSUPPORTED         - The file type cannot be processed by the tool.
    """

    DIRECTLY_PROCESSABLE = "directly_processable"
    CONVERTIBLE = "convertible"
    TEXT_EXTRACTABLE = "text_extractable"
    UNSUPPORTED = "unsupported"


# ---------------------------------------------------------------------------
# Discovery-phase models
# ---------------------------------------------------------------------------


class FileEntry(BaseModel):
    """A file discovered during the scanning phase."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    name: str
    stem: str
    extension: str
    mime_type: Optional[str] = None
    size_bytes: int
    is_symlink: bool = False
    symlink_target: Optional[Path] = None
    category: FileCategory
    parent_folder: Path
    skip_reason: Optional[str] = None


class SymlinkEntry(BaseModel):
    """A symlink that points to a file being renamed."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    symlink_path: Path
    target_path: Path
    is_relative: bool


class FolderEntry(BaseModel):
    """A folder containing files to be renamed."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    name: str
    breadcrumb: str
    depth: int
    file_count: int
    files: list[FileEntry] = []


# ---------------------------------------------------------------------------
# Metadata-extraction models
# ---------------------------------------------------------------------------


class FileMetadata(BaseModel):
    """Extracted metadata for a file.

    Covers document properties (title, author, page count), media properties
    (dimensions, duration, codec), and filesystem timestamps.
    """

    size_bytes: int
    size_human: str
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    accessed_at: Optional[datetime] = None
    permissions: Optional[str] = None

    # Document metadata
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator_application: Optional[str] = None
    page_count: Optional[int] = None
    word_count: Optional[int] = None
    slide_count: Optional[int] = None
    sheet_names: Optional[list[str]] = None

    # Media metadata
    duration_seconds: Optional[float] = None
    dimensions: Optional[str] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    gps_location: Optional[str] = None
    date_taken: Optional[datetime] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    bitrate: Optional[str] = None
    codec: Optional[str] = None


class EnrichedFile(BaseModel):
    """A file with its extracted metadata attached."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    entry: FileEntry
    metadata: FileMetadata
    processed_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Analysis-phase models
# ---------------------------------------------------------------------------


class FolderContext(BaseModel):
    """Context for a folder during the holistic naming phase.

    Groups all enriched files in a single directory together with sibling
    name information so the naming engine can reason about the collection.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    folder_path: Path
    folder_name: str
    breadcrumb: str
    depth: int
    files: list[EnrichedFile]
    sibling_names: list[str]
    file_count: int


class ContentSummary(BaseModel):
    """Structured content summary returned by Gemini."""

    content_type: str
    primary_subject: str
    key_entities: list[str]
    date_references: list[str]
    language: str
    confidence: float


class AnalyzedFile(BaseModel):
    """A file that has been analyzed by Gemini for content understanding."""

    enriched: EnrichedFile
    summary: ContentSummary


# ---------------------------------------------------------------------------
# Rename-proposal models
# ---------------------------------------------------------------------------


class ProposedRename(BaseModel):
    """A proposed rename generated by the holistic naming engine."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    current_name: str
    proposed_name: str
    current_path: Path
    proposed_path: Path
    reasoning: str
    confidence: float
    is_unchanged: bool = False
    has_incoming_symlinks: bool = False
    incoming_symlinks: list[SymlinkEntry] = []


class ValidatedRename(BaseModel):
    """A rename that has passed all validation checks.

    Contains the final name (which may differ from the proposed name due to
    collision resolution) and any symlink updates that need to happen.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    original: ProposedRename
    final_name: str
    validation_notes: list[str] = []
    collision_resolved: bool = False
    symlink_updates: list[tuple[Path, str]] = []


# ---------------------------------------------------------------------------
# Execution-phase models
# ---------------------------------------------------------------------------


class RenameResult(BaseModel):
    """Result of a single rename operation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    old_path: Path
    new_path: Path
    status: str
    error: Optional[str] = None
    symlinks_updated: int = 0


class ExecutionResult(BaseModel):
    """Result of the full execution phase."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    target_directory: Path
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_files: int
    renamed: int
    skipped: int
    failed: int
    symlinks_updated: int
    results: list[RenameResult]
    total_tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Summary / reporting models
# ---------------------------------------------------------------------------


class ImpactSummary(BaseModel):
    """Summary shown to the user before processing begins.

    Provides a clear picture of what the tool intends to do so the user can
    make an informed go / no-go decision.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    target_directory: Path
    recursive: bool
    total_files: int
    supported_files: int
    unsupported_files: int
    symlinks_found: int
    symlink_targets_in_scope: int
    folders_affected: int
    deepest_nesting: int
    estimated_api_calls: int
    estimated_cost_usd: float
    file_type_breakdown: dict[str, int]
    warnings: list[str]


class DiscoveryResult(BaseModel):
    """Complete result of the discovery phase.

    Bundles all discovered files, folders, symlink mappings, and the
    pre-execution impact summary into a single object.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    files: list[FileEntry]
    folders: list[FolderEntry]
    symlink_map: dict[str, list[SymlinkEntry]] = {}  # str key because Path is not hashable in JSON
    impact: ImpactSummary
