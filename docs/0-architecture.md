# Architecture Design Document: AI File Rename Tool

**Version:** 1.0.0
**Date:** 2026-02-26
**Status:** Draft: Awaiting Review
**Companion:** [PRD.md](./PRD.md)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Module Dependency Graph](#2-module-dependency-graph)
3. [Data Flow](#3-data-flow)
4. [Data Models](#4-data-models)
5. [Module Specifications](#5-module-specifications)
6. [Symlink Safety Architecture](#6-symlink-safety-architecture)
7. [File Metadata Extraction Architecture](#7-file-metadata-extraction-architecture)
8. [Concurrency & Multi-Instance Safety](#8-concurrency--multi-instance-safety)
9. [Holistic Naming Engine Design](#9-holistic-naming-engine-design)
10. [Error Propagation & Recovery Architecture](#10-error-propagation--recovery-architecture)
11. [Configuration Resolution Chain](#11-configuration-resolution-chain)
12. [Build & Packaging](#12-build--packaging)
13. [Implementation Sequence](#13-implementation-sequence)

---

## 1. Architecture Overview

### Design Philosophy

The architecture follows a **pipeline pattern**: data flows linearly through a sequence of stateless transformations. Each stage takes structured input and produces structured output. There are no feedback loops, no recursion, and no autonomous decision-making. The LLM is called exactly twice per folder: once for content analysis (batched), once for holistic naming.

```
                    ┌─────────────────────────────────────────────┐
                    │              PIPELINE STAGES                 │
                    │                                              │
                    │  ┌─────────┐  Stateless   ┌──────────────┐  │
  User Input ──────>│  │  Stage  │──────────────>│   Stage      │──>── Output
                    │  │   N     │  Structured   │   N+1        │  │
                    │  └─────────┘  Data Model   └──────────────┘  │
                    │                                              │
                    │  Each stage is a pure function:              │
                    │  f(input_model) -> output_model              │
                    └─────────────────────────────────────────────┘
```

### Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Pipeline vs Agent** | Pipeline | Deterministic, predictable, debuggable. No autonomous loops. |
| **Sync vs Async** | Async with sync wrapper | API calls benefit from concurrency (cross-folder parallelism). CLI is sync. Library exposes both. |
| **State storage** | File-based JSON | No database dependency. Portable. Human-readable for debugging. |
| **Configuration** | YAML + CLI flags + env vars | Layered resolution. YAML for defaults, CLI for overrides, env for secrets. |
| **LLM integration** | google-genai SDK | Unified SDK for both Google AI Studio and Vertex AI. Structured JSON output. |
| **CLI framework** | Click | Mature, composable, supports subcommands, good help text generation. |
| **Output formatting** | Rich | Terminal tables, progress bars, colored output. Optional (graceful degradation). |
| **Data validation** | Pydantic v2 | Type-safe models, JSON schema generation (for Gemini structured output), serialization. |

---

## 2. Module Dependency Graph

```
                              cli.py
                           (entrypoint)
                          /     |      \
                         /      |       \
                        v       v        v
                  config.py  logger.py  constants.py
                       |
                       v
                  discovery.py ──────────> models.py
                       |                      ^
                       v                      |
                  preprocessing.py            |
                       |                      |
                       v                      |
                  metadata.py ────────────────┤
                       |                      |
                       v                      |
                  context.py                  |
                       |                      |
                       v                      |
                  analyzer.py ────────────────┤
                       |                      |
                       v                      |
                  namer.py ───────────────────┤
                       |                      |
                       v                      |
                  validator.py                |
                       |                      |
                       v                      |
                  executor.py ────────> manifest.py
                       |
                       v
                  (complete)
```

**Dependency rules:**
- All modules depend on `models.py` (shared data types).
- All modules depend on `constants.py` (naming rules, format maps).
- `config.py` is read once at startup and threaded through as a parameter.
- `logger.py` is a singleton, configured once at startup.
- No circular dependencies. Data flows strictly downward.

---

## 3. Data Flow

### Complete Data Flow Diagram

```
┌─────────────────┐
│   CLI Invocation │  Input: target_dir, flags
│   cli.py         │
└────────┬────────┘
         │ Config
         v
┌─────────────────┐
│   Discovery      │  Input: target_dir, Config
│   discovery.py   │  Output: DiscoveryResult
│                  │    - List[FileEntry] (all files found)
│                  │    - List[FolderEntry] (all folders)
│                  │    - SymlinkMap (file -> incoming symlinks)
│                  │    - ImpactSummary (counts, types, warnings)
└────────┬────────┘
         │ DiscoveryResult
         v
┌─────────────────┐
│  User Confirm    │  Display ImpactSummary
│  (interactive)   │  Await Y/n
└────────┬────────┘
         │ Confirmed DiscoveryResult
         v
┌─────────────────┐
│  Preprocessing   │  Input: List[FileEntry]
│  preprocessing.py│  Output: List[ProcessedFile]
│                  │    - Converts SVG->PNG, DOCX->PDF, etc.
│                  │    - Populates `processed_path` field
│                  │    - Original file untouched
└────────┬────────┘
         │ List[ProcessedFile]
         v
┌─────────────────┐
│  Metadata        │  Input: List[ProcessedFile]
│  metadata.py     │  Output: List[EnrichedFile]
│                  │    - Extracts os.stat metadata
│                  │    - Extracts format-specific metadata
│                  │    - Populates `metadata` field on each file
└────────┬────────┘
         │ List[EnrichedFile]
         v
┌─────────────────┐
│  Context Builder │  Input: List[EnrichedFile], FolderEntry
│  context.py      │  Output: List[ContextualizedFile]
│                  │    - Adds folder hierarchy breadcrumbs
│                  │    - Adds sibling file names
│                  │    - Groups files by parent folder
└────────┬────────┘
         │ Dict[FolderPath, List[ContextualizedFile]]
         v
┌─────────────────┐
│  Content Analyzer│  Input: Dict[FolderPath, List[ContextualizedFile]]
│  analyzer.py     │  Output: Dict[FolderPath, List[AnalyzedFile]]
│                  │    - Uploads files to Gemini File API
│                  │    - Sends content analysis prompts
│                  │    - Receives structured JSON summaries
│                  │    - Batches small files together
└────────┬────────┘
         │ Dict[FolderPath, List[AnalyzedFile]]
         v
┌─────────────────┐
│  Holistic Namer  │  Input: Dict[FolderPath, List[AnalyzedFile]]
│  namer.py        │  Output: Dict[FolderPath, List[ProposedRename]]
│                  │    - One Gemini call per folder
│                  │    - Considers all files as a cohort
│                  │    - Applies scaling strategy for large folders
└────────┬────────┘
         │ Dict[FolderPath, List[ProposedRename]]
         v
┌─────────────────┐
│  Validator       │  Input: List[ProposedRename]
│  validator.py    │  Output: List[ValidatedRename]
│                  │    - Cross-platform name validation
│                  │    - Collision detection & resolution
│                  │    - Length truncation
│                  │    - Reserved name avoidance
└────────┬────────┘
         │ List[ValidatedRename]
         v
┌─────────────────┐
│  Dry-Run Display │  Input: List[ValidatedRename]
│  (interactive)   │  Display table of proposed renames
│                  │  Await user confirmation
└────────┬────────┘
         │ Approved List[ValidatedRename]
         v
┌─────────────────┐
│  Executor        │  Input: List[ValidatedRename]
│  executor.py     │  Output: ExecutionResult
│                  │    - Creates ephemeral manifest
│                  │    - Atomic rename per file
│                  │    - Updates symlinks if needed
│                  │    - Post-rename verification
│                  │    - Writes global log on completion
│                  │    - Cleans up manifest on success
└────────┬────────┘
         │ ExecutionResult
         v
┌─────────────────┐
│  Summary Report  │  Display final summary
│  cli.py          │  Print cost, duration, counts
└─────────────────┘
```

---

## 4. Data Models

All data models are defined in `models.py` using Pydantic v2.

### Core Models

```python
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime
from enum import Enum
from typing import Optional


class FileCategory(str, Enum):
    """Classification of a file's processability."""
    DIRECTLY_PROCESSABLE = "directly_processable"
    CONVERTIBLE = "convertible"
    TEXT_EXTRACTABLE = "text_extractable"
    UNSUPPORTED = "unsupported"


class FileEntry(BaseModel):
    """A file discovered during the scanning phase."""
    path: Path                           # Absolute path to the file
    name: str                            # Current file name (stem + extension)
    stem: str                            # File name without extension
    extension: str                       # File extension (lowercase, without dot)
    mime_type: Optional[str] = None      # Detected MIME type
    size_bytes: int                      # File size in bytes
    is_symlink: bool = False             # Whether this file is a symlink
    symlink_target: Optional[Path] = None  # Resolved symlink target (if symlink)
    category: FileCategory               # Processing category
    parent_folder: Path                  # Parent directory path
    skip_reason: Optional[str] = None    # Why this file is being skipped (if any)


class SymlinkEntry(BaseModel):
    """A symlink that points to a file being renamed."""
    symlink_path: Path                   # Path to the symlink itself
    target_path: Path                    # Path the symlink points to
    is_relative: bool                    # Whether the symlink uses a relative target


class FolderEntry(BaseModel):
    """A folder containing files to be renamed."""
    path: Path                           # Absolute path to the folder
    name: str                            # Folder name
    breadcrumb: str                      # Full hierarchy path (e.g., "docs > research > ml")
    depth: int                           # Nesting depth from target root
    file_count: int                      # Number of processable files
    files: list[FileEntry] = []          # Files in this folder


class FileMetadata(BaseModel):
    """Extracted metadata for a file (both OS-level and format-specific)."""
    # Universal (os.stat)
    size_bytes: int
    size_human: str                      # e.g., "4.2 MB"
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    accessed_at: Optional[datetime] = None
    permissions: Optional[str] = None

    # Format-specific (best-effort, all optional)
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator_application: Optional[str] = None
    page_count: Optional[int] = None
    word_count: Optional[int] = None
    slide_count: Optional[int] = None
    sheet_names: Optional[list[str]] = None
    duration_seconds: Optional[float] = None
    dimensions: Optional[str] = None     # e.g., "3840x2160"
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    gps_location: Optional[str] = None   # Reverse-geocoded location string
    date_taken: Optional[datetime] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    bitrate: Optional[str] = None
    codec: Optional[str] = None


class EnrichedFile(BaseModel):
    """A file with its metadata attached."""
    entry: FileEntry
    metadata: FileMetadata
    processed_path: Optional[Path] = None  # Path to converted file (if converted)


class ContentSummary(BaseModel):
    """Structured content summary returned by Gemini content analysis."""
    content_type: str                    # "photograph", "document", "presentation", etc.
    primary_subject: str                 # 2-3 sentence description
    key_entities: list[str]              # Extracted entities
    date_references: list[str]           # Dates found in content or metadata
    language: str                        # Detected language
    confidence: float                    # 0.0 - 1.0


class AnalyzedFile(BaseModel):
    """A file that has been analyzed by Gemini."""
    enriched: EnrichedFile
    summary: ContentSummary


class ProposedRename(BaseModel):
    """A proposed rename generated by the holistic naming engine."""
    current_name: str
    proposed_name: str
    current_path: Path
    proposed_path: Path
    reasoning: str                       # Why this name was chosen
    confidence: float                    # 0.0 - 1.0
    is_unchanged: bool = False           # True if current name was kept
    has_incoming_symlinks: bool = False   # True if symlinks point to this file
    incoming_symlinks: list[SymlinkEntry] = []


class ValidatedRename(BaseModel):
    """A rename that has passed all validation checks."""
    original: ProposedRename
    final_name: str                      # May differ from proposed_name after validation
    validation_notes: list[str] = []     # Any modifications made during validation
    collision_resolved: bool = False     # Whether a name collision was resolved
    symlink_updates: list[tuple[Path, str]] = []  # [(symlink_path, new_target_name)]


class RenameResult(BaseModel):
    """Result of a single rename operation."""
    old_path: Path
    new_path: Path
    status: str                          # "completed", "failed", "skipped"
    error: Optional[str] = None
    symlinks_updated: int = 0


class ExecutionResult(BaseModel):
    """Result of the full execution phase."""
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


class ImpactSummary(BaseModel):
    """Summary shown to user before processing begins."""
    target_directory: Path
    recursive: bool
    total_files: int
    supported_files: int
    unsupported_files: int
    symlinks_found: int
    symlink_targets_in_scope: int        # Files that ARE symlink targets (need extra care)
    folders_affected: int
    deepest_nesting: int
    estimated_api_calls: int
    estimated_cost_usd: float
    file_type_breakdown: dict[str, int]  # extension -> count
    warnings: list[str]                  # Any warnings to show user
```

---

## 5. Module Specifications

### 5.1 `cli.py`: CLI Entrypoint

**Responsibility:** Parse CLI arguments, wire up the pipeline, manage interactive prompts.

```python
# Key interfaces

@click.group()
def main():
    """AI-powered file renaming tool."""
    pass

@main.command()
@click.argument("target_directory", type=click.Path(exists=True))
@click.option("--recursive", "-r", is_flag=True)
@click.option("--execute", "-x", is_flag=True)
@click.option("--headless", "-H", is_flag=True)
@click.option("--config", "-c", type=click.Path())
@click.option("--model", "-m", default="gemini-2.0-flash")
@click.option("--max-files", default=500, type=int)
@click.option("--custom-instructions", "-i", default=None)
@click.option("--verbose", "-v", is_flag=True)
@click.option("--cost-limit", default=5.00, type=float)
def rename(target_directory, **kwargs):
    """Rename files using AI-powered content analysis."""
    pass

@main.command()
@click.argument("target_directory", type=click.Path(exists=True), required=False)
def undo(target_directory):
    """Undo the last rename operation."""
    pass

@main.command()
@click.option("--directory", "-d", default=None)
@click.option("--last", "-n", default=10, type=int)
@click.option("--json", "as_json", is_flag=True)
def history(directory, last, as_json):
    """View rename history."""
    pass
```

**Design notes:**
- The CLI calls pipeline functions in sequence but does NOT contain business logic.
- Interactive prompts (confirmation, dry-run review) happen in `cli.py`.
- In headless mode, all prompts are auto-confirmed.
- The `rename` command orchestrates the full pipeline. It is the only place where all modules are composed.

### 5.2 `discovery.py`: File System Scanner

**Responsibility:** Walk the target directory, classify every file, detect symlinks, build the inventory.

```python
# Key interface

def discover(
    target_dir: Path,
    recursive: bool,
    config: Config
) -> DiscoveryResult:
    """
    Scan target directory and return complete inventory.

    Returns:
        DiscoveryResult containing:
        - files: List of all FileEntry objects
        - folders: List of all FolderEntry objects
        - symlink_map: Dict mapping file paths to incoming symlinks
        - impact: ImpactSummary for user display
    """
```

**Key behaviors:**
- Uses `pathlib.Path.iterdir()` (or `rglob("*")` for recursive).
- Classifies each file using `constants.FORMAT_CATEGORIES`.
- Detects symlinks via `Path.is_symlink()`.
- Builds reverse symlink map: for each regular file, which symlinks point to it.
- Applies exclude patterns from config.
- Applies `--max-files` safety limit.
- Does NOT read file contents: only file system metadata.

### 5.3 `preprocessing.py`: Format Converter

**Responsibility:** Convert files that Gemini cannot process natively into processable formats.

```python
# Key interface

def preprocess(
    files: list[FileEntry],
    temp_dir: Path,
    config: Config
) -> list[ProcessedFile]:
    """
    Convert files to Gemini-compatible formats where needed.

    Files that are already processable pass through unchanged.
    Converted files get a `processed_path` pointing to the temp copy.
    Original files are NEVER modified.
    """
```

**Conversion dispatch table:**

```python
CONVERSION_MAP = {
    "svg": ("png", convert_svg_to_png),      # cairosvg
    "gif": ("png", convert_gif_to_png),      # Pillow (first frame)
    "bmp": ("png", convert_bmp_to_png),      # Pillow
    "tiff": ("png", convert_tiff_to_png),    # Pillow
    "tif": ("png", convert_tiff_to_png),     # Pillow
    "docx": ("pdf", convert_office_to_pdf),  # LibreOffice headless
    "pptx": ("pdf", convert_office_to_pdf),  # LibreOffice headless
    "xlsx": ("pdf", convert_office_to_pdf),  # LibreOffice headless
    "doc": ("pdf", convert_office_to_pdf),   # LibreOffice headless
    "ppt": ("pdf", convert_office_to_pdf),   # LibreOffice headless
    "xls": ("pdf", convert_office_to_pdf),   # LibreOffice headless
}
```

**Design notes:**
- All conversions write to a dedicated temp directory (auto-cleaned on exit).
- If a conversion tool is not installed (e.g., LibreOffice), the file is marked as `TEXT_EXTRACTABLE` fallback and the user is warned.
- Conversion errors are non-fatal: the file is skipped with a warning.

### 5.4 `metadata.py`: Metadata Extractor

**Responsibility:** Extract both OS-level and format-specific metadata from each file.

```python
# Key interface

def extract_metadata(file: FileEntry) -> FileMetadata:
    """
    Extract all available metadata from a file.

    Always returns at minimum os.stat metadata.
    Format-specific metadata is best-effort.
    Times out after 5 seconds per file.
    """
```

**Extraction dispatch:**

```python
METADATA_EXTRACTORS = {
    # Image EXIF
    "jpeg": extract_image_exif,
    "jpg": extract_image_exif,
    "png": extract_image_metadata,  # PNG has limited metadata
    "heic": extract_image_exif,
    "tiff": extract_image_exif,

    # Documents
    "pdf": extract_pdf_metadata,
    "docx": extract_docx_metadata,
    "pptx": extract_pptx_metadata,
    "xlsx": extract_xlsx_metadata,

    # Audio
    "mp3": extract_audio_metadata,
    "wav": extract_audio_metadata,
    "flac": extract_audio_metadata,
    "ogg": extract_audio_metadata,
    "aac": extract_audio_metadata,

    # Video
    "mp4": extract_video_metadata,
    "mov": extract_video_metadata,
    "avi": extract_video_metadata,
    "mkv": extract_video_metadata,
    "webm": extract_video_metadata,
}
```

**Design notes:**
- Each extractor function is wrapped in a try/except: if extraction fails, it returns an empty `FileMetadata` with only `os.stat` data.
- Each extractor has a 5-second timeout (using `signal.alarm` on POSIX, threading on Windows).
- Libraries are imported lazily: if `Pillow` is not installed, image EXIF extraction gracefully degrades to size/dates only.
- GPS reverse geocoding is optional (requires `reverse_geocoder` library).

### 5.5 `context.py`: Context Builder

**Responsibility:** Enrich files with folder hierarchy context and group them by parent folder.

```python
# Key interface

def build_context(
    files: list[EnrichedFile],
    target_root: Path
) -> dict[Path, FolderContext]:
    """
    Group files by parent folder and build context for each group.

    Returns a dict mapping folder paths to FolderContext objects,
    where each FolderContext contains the folder's breadcrumb,
    the list of files, and sibling file names.
    """
```

**FolderContext model:**

```python
class FolderContext(BaseModel):
    folder_path: Path
    folder_name: str
    breadcrumb: str                # "hard-drive > documents > work > 2023"
    depth: int
    files: list[EnrichedFile]
    sibling_names: list[str]       # Names of ALL files in this folder
    file_count: int
```

### 5.6 `analyzer.py`: Content Analyzer (Gemini)

**Responsibility:** Send files to Gemini for content analysis. The first of two LLM calls.

```python
# Key interface

async def analyze_folder(
    folder: FolderContext,
    client: genai.Client,
    model: str,
    config: Config
) -> list[AnalyzedFile]:
    """
    Analyze all files in a folder using Gemini.

    Files are batched by size for efficiency.
    Each API call returns structured JSON content summaries.
    """

async def analyze_all(
    folders: dict[Path, FolderContext],
    client: genai.Client,
    model: str,
    config: Config,
    concurrency: int = 3
) -> dict[Path, list[AnalyzedFile]]:
    """
    Analyze all folders concurrently (within concurrency limit).
    """
```

**Batching strategy:**

```python
def create_batches(files: list[EnrichedFile], max_batch_bytes: int = 80_000_000) -> list[list[EnrichedFile]]:
    """
    Group files into batches that fit within the Gemini request size limit.

    Strategy:
    1. Sort files by size ascending.
    2. Greedily add files to current batch until size limit is approached.
    3. Start a new batch.

    Text-extractable files are batched separately (no upload needed).
    """
```

**Prompt construction:**
- The prompt template is in `constants.py`.
- Metadata is serialized to JSON and injected into the prompt context block.
- For text-extractable files, the file content (first N lines/bytes) is included inline instead of uploading.

### 5.7 `namer.py`: Holistic Naming Engine (Gemini)

**Responsibility:** Generate names for ALL files in a folder as a cohort. The second of two LLM calls.

```python
# Key interface

async def name_folder(
    folder_path: Path,
    analyzed_files: list[AnalyzedFile],
    folder_context: FolderContext,
    client: genai.Client,
    model: str,
    config: Config
) -> list[ProposedRename]:
    """
    Generate holistic names for all files in a single folder.

    Applies the appropriate scaling strategy based on file count:
    - 1-50: Full holistic (single prompt)
    - 51-200: Clustered holistic
    - 201-500: Sampled holistic
    - 500+: Progressive holistic
    """
```

**Scaling strategies (implemented as strategy pattern):**

```python
class NamingStrategy(Protocol):
    async def generate_names(
        self,
        files: list[AnalyzedFile],
        context: FolderContext,
        client: genai.Client,
        model: str,
        config: Config
    ) -> list[ProposedRename]: ...

class FullHolisticStrategy(NamingStrategy):
    """For folders with 1-50 files. Single LLM call."""
    ...

class ClusteredHolisticStrategy(NamingStrategy):
    """For folders with 51-200 files. Cluster by content type, then name each cluster."""
    ...

class SampledHolisticStrategy(NamingStrategy):
    """For folders with 201-500 files. Sample, establish patterns, then apply."""
    ...

class ProgressiveHolisticStrategy(NamingStrategy):
    """For folders with 500+ files. Sequential batches with accumulated context."""
    ...

def select_strategy(file_count: int) -> NamingStrategy:
    if file_count <= 50:
        return FullHolisticStrategy()
    elif file_count <= 200:
        return ClusteredHolisticStrategy()
    elif file_count <= 500:
        return SampledHolisticStrategy()
    else:
        return ProgressiveHolisticStrategy()
```

### 5.8 `validator.py`: Name Validator

**Responsibility:** Ensure all proposed names are valid, unique, and cross-platform safe.

```python
# Key interface

def validate_renames(
    renames: list[ProposedRename],
    symlink_map: dict[Path, list[SymlinkEntry]]
) -> list[ValidatedRename]:
    """
    Validate and sanitize all proposed renames.

    Checks:
    1. Cross-platform character validation
    2. Length limits
    3. Reserved name avoidance
    4. Collision detection within the folder
    5. Collision detection with existing files NOT being renamed
    6. Symlink update planning
    """
```

**Collision resolution:**

```python
def resolve_collisions(renames: list[ProposedRename]) -> list[ProposedRename]:
    """
    If two files get the same proposed name, append numeric suffixes.

    Example:
      report.pdf, report.pdf -> report.pdf, report-2.pdf

    Suffixes start at 2 (the first file keeps the clean name).
    """
```

### 5.9 `executor.py`: Safe Rename Executor

**Responsibility:** Execute renames atomically with manifest tracking.

```python
# Key interface

def execute_renames(
    renames: list[ValidatedRename],
    manifest_dir: Path,
    config: Config
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
    On completion: write global log, clean up manifest.
    """

def undo_renames(manifest_path: Path) -> ExecutionResult:
    """
    Reverse all renames recorded in a manifest file.
    Processes in reverse order.
    """
```

### 5.10 `manifest.py`: Ephemeral State Manager

**Responsibility:** Manage the working manifest file for crash recovery and undo.

```python
# Key interface

class Manifest:
    def __init__(self, directory: Path, run_id: str):
        self.path = directory / ".ai-rename-manifest.json"
        self.run_id = run_id
        self._data = {}

    def create(self, renames: list[ValidatedRename]) -> None:
        """Create the manifest with all renames in 'pending' status."""

    def record_intent(self, index: int) -> None:
        """Mark a rename as 'in_progress' before executing."""

    def record_success(self, index: int) -> None:
        """Mark a rename as 'completed' after verification."""

    def record_failure(self, index: int, error: str) -> None:
        """Mark a rename as 'failed' with error details."""

    def flush(self) -> None:
        """Force write to disk. Called after every state change."""

    def cleanup(self) -> None:
        """Delete the manifest file (called on successful completion)."""

    @classmethod
    def load_existing(cls, directory: Path) -> Optional["Manifest"]:
        """Load an existing manifest from a previous run."""

    @property
    def is_complete(self) -> bool:
        """True if all renames are completed."""

    @property
    def is_interrupted(self) -> bool:
        """True if some renames are pending/in_progress (crash recovery)."""
```

**Design notes:**
- The manifest file is written atomically: write to a temp file, then `os.replace()` to the final path.
- `flush()` calls `os.fsync()` to ensure data reaches disk.
- The manifest file is hidden (`.ai-rename-manifest.json`) to avoid clutter.

### 5.11 `logger.py`: Dual-Level Logger

**Responsibility:** Manage both session logging and the global rename history.

```python
# Key interface

class RenameLogger:
    def __init__(self, log_dir: Path, run_id: str, verbose: bool = False):
        self.session_log = log_dir / f"session-{run_id}.log"
        self.history_log = log_dir / "rename-history.jsonl"

    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...

    def append_to_history(self, result: ExecutionResult) -> None:
        """
        Append a completed execution result to the global history log.
        Uses file locking for multi-instance safety.
        """

    def query_history(
        self,
        directory: Optional[Path] = None,
        last_n: int = 10
    ) -> list[dict]:
        """Query the global history log with optional filters."""
```

### 5.12 `config.py`: Configuration Manager

**Responsibility:** Resolve configuration from multiple sources.

```python
# Key interface

class Config(BaseModel):
    """Resolved configuration. Immutable after creation."""
    # Auth
    gemini_api_key: str
    use_vertex_ai: bool = False
    vertex_project: Optional[str] = None
    vertex_location: Optional[str] = None

    # Model
    model: str = "gemini-2.0-flash"

    # Naming
    max_words: int = 8
    min_words: int = 2
    separator: str = "-"
    include_dates: bool = True
    language: str = "en"
    custom_instructions: Optional[str] = None

    # Safety
    max_files: int = 500
    cost_limit: float = 5.00
    require_confirmation: bool = True

    # Processing
    concurrency: int = 3
    convert_office_docs: bool = True

    # Logging
    log_level: str = "INFO"
    log_dir: Path = Path("~/.ai-rename/logs/").expanduser()

    # Exclude
    exclude_patterns: list[str] = [
        ".*", "*.tmp", "node_modules", "__pycache__", ".git"
    ]

def load_config(
    config_path: Optional[Path] = None,
    cli_overrides: dict = {}
) -> Config:
    """
    Load configuration with precedence:
    1. CLI flags (highest)
    2. Environment variables
    3. Config file (~/.ai-rename.yaml)
    4. Defaults (lowest)
    """
```

---

## 6. Symlink Safety Architecture

### The Problem

When renaming a regular file, any symlinks that point to that file by name (relative symlinks) or by path (absolute symlinks within the same directory) will break. This is because the symlink stores the *name/path* of the target, and after renaming, that name no longer exists.

### Empirical Findings

Tested on macOS (POSIX semantics apply to Linux as well):

| Scenario | Result |
|----------|--------|
| Rename a symlink itself | **SAFE.** The symlink's target is unchanged. Link still works. |
| Rename a file with relative symlink pointing to it | **BREAKS.** Symlink target `real-file.txt` no longer exists after rename to `new-name.txt`. |
| Rename a file with absolute symlink pointing to it | **BREAKS.** Same: the stored path no longer resolves. |
| `os.rename()` on symlink | Renames the link, not the target. Correct behavior. |

### Architecture Decision

The tool DOES process and rename symlinks. It also handles the case where regular files being renamed have incoming symlinks.

### Symlink Discovery Phase

During `discovery.py`, the tool builds a **reverse symlink map**:

```python
def build_symlink_map(target_dir: Path, recursive: bool) -> dict[Path, list[SymlinkEntry]]:
    """
    Scan for all symlinks and build a reverse map:
    resolved_target_path -> [symlinks pointing to it]

    This map tells us, for any file we're about to rename,
    which symlinks will break and need updating.
    """
    symlink_map: dict[Path, list[SymlinkEntry]] = {}

    for item in iterate_directory(target_dir, recursive):
        if item.is_symlink():
            target = item.resolve()  # Resolve to actual file
            raw_target = os.readlink(item)
            is_relative = not Path(raw_target).is_absolute()

            entry = SymlinkEntry(
                symlink_path=item,
                target_path=target,
                is_relative=is_relative
            )

            symlink_map.setdefault(target, []).append(entry)

    return symlink_map
```

### Symlink Update Protocol

During the execution phase, after renaming a file that has incoming symlinks:

```python
def update_symlinks_for_rename(
    old_path: Path,
    new_path: Path,
    symlink_entries: list[SymlinkEntry]
) -> list[tuple[Path, bool]]:
    """
    Update all symlinks that pointed to old_path to point to new_path.

    Returns list of (symlink_path, success) tuples.
    """
    results = []
    new_name = new_path.name

    for entry in symlink_entries:
        symlink = entry.symlink_path

        if not symlink.is_symlink():
            # Symlink was itself renamed or removed: skip
            results.append((symlink, False))
            continue

        if entry.is_relative:
            # Relative symlink: just update the filename portion
            new_target = new_name
        else:
            # Absolute symlink: update the full path
            new_target = str(new_path)

        # Atomic symlink update: remove old, create new
        temp_link = symlink.with_suffix(".ai-rename-tmp")
        os.symlink(new_target, temp_link)
        os.replace(temp_link, symlink)

        results.append((symlink, True))

    return results
```

### Symlink Handling in Dry-Run

The dry-run preview highlights files that have incoming symlinks:

```
╔═══════════════════════════════════════════════════════════════╗
║  #  │ Current Name     │ Proposed Name        │ Notes        ║
║  ───┼──────────────────┼──────────────────────┼────────────── ║
║   1 │ report.pdf       │ q3-revenue-2023.pdf  │ ⚠ 2 symlinks ║
║   2 │ link-to-report   │ (symlink, renamed)   │ -> report.pdf║
╚═══════════════════════════════════════════════════════════════╝

⚠ 2 symlinks point to "report.pdf" and will be updated:
  - /Users/user/desktop/report-shortcut -> report.pdf
  - /Users/user/shared/latest-report -> report.pdf
```

### Symlinks Outside Scope

If a symlink pointing to a file being renamed exists OUTSIDE the target directory (e.g., on the Desktop when we're renaming files in `~/documents/`), the tool **cannot detect it** (it only scans the target directory). This is a known limitation and is documented as a warning when symlinks are present:

```
⚠ WARNING: Symlinks pointing to these files from OUTSIDE the target
  directory will NOT be detected or updated. If you have symlinks
  on your Desktop or elsewhere pointing to files in this folder,
  they will break after renaming.
```

---

## 7. File Metadata Extraction Architecture

### Extraction Pipeline

```
FileEntry
    │
    ├── os.stat() ──────────────> UniversalMetadata (always succeeds)
    │                                 - size, dates, permissions
    │
    ├── extension lookup ────────> ExtractorFunction (may not exist)
    │   METADATA_EXTRACTORS[ext]       - format-specific metadata
    │                                  - 5-second timeout
    │                                  - try/except wrapped
    │
    └── Merge ───────────────────> FileMetadata (complete model)
```

### Lazy Import Pattern

To keep the tool lightweight, metadata libraries are imported lazily:

```python
def extract_image_exif(file_path: Path) -> dict:
    """Extract EXIF data from JPEG/HEIC/TIFF images."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
    except ImportError:
        return {}  # Pillow not installed: graceful degradation

    # ... extraction logic ...
```

This means:
- The core tool works with ZERO optional dependencies (just `google-genai`, `click`, `rich`, `pydantic`, `pyyaml`).
- Each optional dependency unlocks richer metadata for specific file types.
- Missing libraries produce a single warning at startup, not per-file errors.

### Metadata Availability Matrix

| Metadata Field | Requires | Files |
|---------------|----------|-------|
| size, dates, permissions | Nothing (stdlib) | All |
| Image EXIF (camera, GPS, date taken) | `Pillow` | JPEG, HEIC, TIFF |
| Image dimensions | `Pillow` | JPEG, PNG, WebP, HEIC, GIF, BMP, TIFF |
| PDF metadata (title, author, pages) | `PyPDF2` or `pdfplumber` | PDF |
| DOCX metadata (title, author, word count) | `python-docx` | DOCX |
| PPTX metadata (title, author, slide count) | `python-pptx` | PPTX |
| XLSX metadata (title, author, sheet names) | `openpyxl` | XLSX |
| Audio metadata (title, artist, duration) | `mutagen` | MP3, WAV, FLAC, OGG, AAC |
| Video metadata (duration, resolution, codec) | `mutagen` or `ffprobe` | MP4, MOV, AVI, MKV, WebM |
| GPS reverse geocoding | `reverse_geocoder` | Any file with GPS EXIF |

### Metadata in Prompt Context

The extracted metadata is serialized to a compact JSON representation and injected into the Gemini content analysis prompt:

```python
def format_metadata_for_prompt(metadata: FileMetadata) -> str:
    """
    Format metadata as a concise context block for the Gemini prompt.
    Excludes null/empty fields to keep the prompt compact.
    """
    context = {}

    if metadata.title:
        context["title"] = metadata.title
    if metadata.author:
        context["author"] = metadata.author
    if metadata.created_at:
        context["created"] = metadata.created_at.strftime("%Y-%m-%d")
    if metadata.modified_at:
        context["modified"] = metadata.modified_at.strftime("%Y-%m-%d")
    if metadata.page_count:
        context["pages"] = metadata.page_count
    if metadata.duration_seconds:
        context["duration"] = format_duration(metadata.duration_seconds)
    if metadata.dimensions:
        context["dimensions"] = metadata.dimensions
    if metadata.camera_model:
        context["camera"] = f"{metadata.camera_make} {metadata.camera_model}"
    if metadata.gps_location:
        context["location"] = metadata.gps_location
    if metadata.artist:
        context["artist"] = metadata.artist
    if metadata.album:
        context["album"] = metadata.album

    if not context:
        return "null"

    return json.dumps(context, indent=2)
```

---

## 8. Concurrency & Multi-Instance Safety

### Problem

The user may run multiple instances of the tool simultaneously against different directories. For example:

```bash
# Terminal 1
ai-rename ~/documents/research/ --headless --execute &

# Terminal 2
ai-rename ~/photos/vacation-2023/ --headless --execute &

# Terminal 3
ai-rename ~/work/projects/ --headless --execute &
```

All three instances must:
1. Write to the global log file without corruption.
2. Have unique run IDs that don't collide.
3. Not interfere with each other's manifests (since manifests are per-directory, this is already isolated).

### Global Log File Locking

```python
import fcntl  # POSIX
import json

def append_to_history_log(log_path: Path, record: dict) -> None:
    """
    Append a single JSON record to the JSONL log file.
    Uses file locking to prevent corruption from concurrent writes.
    """
    line = json.dumps(record, default=str) + "\n"

    with open(log_path, "a") as f:
        # Acquire exclusive lock
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        finally:
            # Release lock
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

**Cross-platform locking:**

```python
import sys

if sys.platform == "win32":
    import msvcrt

    def lock_file(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def unlock_file(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def lock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)

    def unlock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

### Run ID Generation

```python
import uuid
from datetime import datetime

def generate_run_id() -> str:
    """
    Generate a unique run ID.
    Format: {date}-{short-uuid}
    Example: "20260226-a7f3b2c1"
    """
    date_part = datetime.now().strftime("%Y%m%d")
    uuid_part = uuid.uuid4().hex[:8]
    return f"{date_part}-{uuid_part}"
```

### Manifest Isolation

Manifests are stored in the target directory (`.ai-rename-manifest.json`), so multiple instances targeting different directories have naturally isolated state. If two instances somehow target the same directory:

1. The second instance detects the existing manifest from the first.
2. It reports: "Another rename operation is in progress in this directory."
3. It refuses to proceed until the manifest is resolved (completed, undone, or discarded).

This is enforced by checking for an existing manifest at the start of the execution phase.

### API Rate Limit Coordination

Multiple instances share the same API key and therefore the same rate limits. Each instance independently tracks its own call rate. If an instance hits a rate limit error (HTTP 429), it backs off with exponential retry. There is no cross-instance coordination: each instance handles rate limits independently, which is sufficient for the expected usage pattern (a few concurrent instances, not hundreds).

---

## 9. Holistic Naming Engine Design

### Strategy Pattern Implementation

```
                    ┌─────────────────────┐
                    │   select_strategy()  │
                    │   file_count → impl  │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐────────────────┐
              │                │                │                │
              v                v                v                v
     ┌────────────┐   ┌──────────────┐  ┌───────────┐  ┌──────────────┐
     │   Full     │   │  Clustered   │  │  Sampled  │  │ Progressive  │
     │ Holistic   │   │  Holistic    │  │ Holistic  │  │  Holistic    │
     │ (1-50)     │   │  (51-200)    │  │ (201-500) │  │  (500+)      │
     └────────────┘   └──────────────┘  └───────────┘  └──────────────┘
```

### Full Holistic Strategy (1-50 files)

The simplest case. All file summaries fit in a single prompt.

```
[System instruction + naming rules]
[Folder context: path, hierarchy, name]
[File 1: current_name, content_type, summary, entities, dates]
[File 2: ...]
...
[File N: ...]
[Response format instruction]
```

**Token budget estimate:** ~200 tokens per file summary, ~500 tokens for instructions/context. 50 files ≈ 10,500 input tokens. Well within model limits.

### Clustered Holistic Strategy (51-200 files)

1. **Cluster files by content type** (all images together, all PDFs together, etc.).
2. If a content type cluster is still >50, sub-cluster by keyword similarity from summaries.
3. **Generate a folder overview** summarizing all clusters.
4. **Name each cluster** with the folder overview as preamble:

```
FOLDER OVERVIEW:
This folder contains 150 files across 4 groups:
- Group A: 45 photographs (nature, travel)
- Group B: 60 PDF documents (research papers)
- Group C: 30 presentations (conference talks)
- Group D: 15 spreadsheets (financial data)

You are naming Group A (45 photographs).
The other groups have these names already assigned: [list]

FILE SUMMARIES FOR GROUP A:
[File 1: ...]
...
```

### Sampled Holistic Strategy (201-500 files)

1. **Sample ~50 representative files** (stratified by content type).
2. **Name the sample holistically** (single prompt, like Full Holistic).
3. **Extract naming patterns** from the sample results.
4. **Apply patterns** to remaining files individually, with collision detection.

The "pattern extraction" step sends the sample results back to the LLM:

```
You named 50 files in this folder. Here are the names you chose:
[list of 50 names]

Now name these additional files following the same style and patterns.
Avoid duplicating any of the names above.
[remaining files]
```

### Progressive Holistic Strategy (500+ files)

1. **Split into batches of 50.**
2. **Name batch 1** holistically (normal Full Holistic).
3. **Name batch 2** holistically, with batch 1's names as context:
   ```
   Previously named files in this folder:
   [batch 1 names]

   Now name this next batch:
   [batch 2 files]
   ```
4. Continue until all batches are named.
5. Each successive batch has the cumulative list of all prior names as context.

**Context window management:** As the cumulative name list grows, only the names (not full summaries) of prior batches are included. At 500+ files, the prior name list is ~5,000 tokens: manageable.

---

## 10. Error Propagation & Recovery Architecture

### Error Categories

```python
class RenameError(Exception):
    """Base exception for all rename errors."""
    pass

class DiscoveryError(RenameError):
    """Target directory not found, permissions, etc."""
    pass

class PreprocessingError(RenameError):
    """Conversion failure (LibreOffice not installed, corrupt file, etc.)."""
    severity: str = "warning"  # Non-fatal: skip file, continue

class MetadataExtractionError(RenameError):
    """Metadata extraction failure."""
    severity: str = "debug"  # Non-fatal: proceed with minimal metadata

class AnalysisError(RenameError):
    """Gemini API failure after retries."""
    severity: str = "warning"  # Non-fatal: skip file, continue

class NamingError(RenameError):
    """Holistic naming prompt failure."""
    severity: str = "error"  # Fatal for the folder (can't name any files)

class ValidationError(RenameError):
    """Name validation failure (should not happen: indicates bug)."""
    severity: str = "error"

class ExecutionError(RenameError):
    """os.rename() failure."""
    severity: str = "critical"  # Halt batch, preserve manifest
```

### Error Propagation Rules

| Stage | Error Behavior |
|-------|---------------|
| Discovery | Fatal. If target dir is invalid, abort entirely. |
| Preprocessing | Per-file. Skip file with warning, continue with others. |
| Metadata | Per-file. Proceed with minimal metadata, log at debug level. |
| Analysis | Per-file. Skip file with warning. If ALL files in a folder fail, skip the folder. |
| Naming | Per-folder. If the naming prompt fails, skip the entire folder with an error. |
| Validation | Should never fail (it sanitizes, not rejects). If it does, it's a bug: abort. |
| Execution | Per-file. Halt the ENTIRE batch on first failure. Preserve manifest. |

### Recovery State Machine

```
                    ┌─────────────┐
         ┌────────>│   CLEAN     │<────────────────────┐
         │         │ (no manifest)│                     │
         │         └──────┬──────┘                     │
         │                │ Start new run              │
         │                v                            │
         │         ┌─────────────┐                     │
         │         │  RUNNING    │                     │
         │         │ (manifest   │                     │
         │         │  exists,    │                     │
         │         │  in_progress)│                     │
         │         └──────┬──────┘                     │
         │                │                            │
         │           ┌────┴────┐                       │
         │           │         │                       │
         │     Success      Failure/Crash              │
         │           │         │                       │
         │           v         v                       │
         │    ┌───────────┐  ┌───────────────┐         │
         │    │ COMPLETED │  │  INTERRUPTED  │         │
         │    │(manifest  │  │ (manifest     │         │
         │    │ complete) │  │  partial)     │         │
         │    └─────┬─────┘  └──────┬───────┘         │
         │          │               │                  │
         │     ┌────┴────┐    ┌────┴────┐              │
         │     │         │    │    │    │              │
         │   Confirm   Undo  Resume Undo  Discard     │
         │     │         │    │    │    │              │
         │     v         v    │    v    v              │
         └─ Delete    Reverse │  Reverse  Delete ─────┘
            manifest  renames │  renames  manifest
                      Delete  │  Delete
                      manifest│  manifest
                              │
                              └──> Continue executing
                                   remaining renames
```

---

## 11. Configuration Resolution Chain

```
Priority (highest to lowest):

┌─────────────────────────────────────┐
│  1. CLI flags                        │  --model gemini-2.5-pro
│     Explicit user intent for this    │  --max-files 1000
│     specific invocation              │  --custom-instructions "..."
├─────────────────────────────────────┤
│  2. Environment variables            │  GEMINI_API_KEY=...
│     Machine-level configuration      │  AI_RENAME_MODEL=...
│     Good for CI/CD and secrets       │
├─────────────────────────────────────┤
│  3. Config file                      │  ~/.ai-rename.yaml
│     User-level defaults              │  (or path from --config)
│     Persistent preferences           │
├─────────────────────────────────────┤
│  4. Built-in defaults                │  model: gemini-2.0-flash
│     Hardcoded in config.py           │  max_files: 500
│     Always available                 │  separator: "-"
└─────────────────────────────────────┘

Resolution algorithm:
  for each config field:
    value = cli_flags.get(field)
        or env_vars.get(f"AI_RENAME_{field.upper()}")
        or yaml_config.get(field)
        or DEFAULT_VALUES[field]
```

### Environment Variable Mapping

| Config Field | Environment Variable | CLI Flag |
|-------------|---------------------|----------|
| `gemini_api_key` | `GEMINI_API_KEY` | `--api-key` |
| `model` | `AI_RENAME_MODEL` | `--model` |
| `max_files` | `AI_RENAME_MAX_FILES` | `--max-files` |
| `log_level` | `AI_RENAME_LOG_LEVEL` | `--log-level` |
| `concurrency` | `AI_RENAME_CONCURRENCY` | N/A |

---

## 12. Build & Packaging

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ai-file-rename"
version = "1.0.0"
description = "AI-powered file renaming using Google Gemini"
requires-python = ">=3.10"
license = "MIT"

dependencies = [
    "google-genai>=1.0.0",
    "click>=8.0",
    "rich>=13.0",
    "pydantic>=2.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
# Metadata extraction
images = ["Pillow>=10.0"]
pdf = ["PyPDF2>=3.0"]
office = ["python-docx>=1.0", "python-pptx>=1.0", "openpyxl>=3.1"]
audio = ["mutagen>=1.47"]
geo = ["reverse_geocoder>=1.5"]
svg = ["cairosvg>=2.7"]

# All metadata extractors
full = [
    "ai-file-rename[images]",
    "ai-file-rename[pdf]",
    "ai-file-rename[office]",
    "ai-file-rename[audio]",
    "ai-file-rename[geo]",
    "ai-file-rename[svg]",
]

# Development
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "ruff>=0.1.0",
]

[project.scripts]
ai-rename = "ai_file_rename.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/ai_file_rename"]
```

### Installation Commands

```bash
# Minimal (core only)
pip install ai-file-rename

# With all metadata extractors
pip install ai-file-rename[full]

# Cherry-pick capabilities
pip install ai-file-rename[images,pdf,audio]

# Development
pip install -e ".[dev,full]"
```

---

## 13. Implementation Sequence

### Recommended Build Order

The modules should be implemented in this order, with each step building on the previous:

```
Phase 1: Foundation
├── Step 1: models.py + constants.py    (data types, format maps, naming rules)
├── Step 2: config.py                    (configuration loading)
├── Step 3: validator.py                 (name validation, can be tested independently)
└── Step 4: logger.py                    (logging infrastructure)

Phase 2: Pipeline Stages
├── Step 5: discovery.py                 (file scanning, symlink detection)
├── Step 6: metadata.py                  (metadata extraction)
├── Step 7: preprocessing.py             (format conversion)
├── Step 8: context.py                   (folder hierarchy, grouping)
├── Step 9: analyzer.py                  (Gemini content analysis)
└── Step 10: namer.py                    (holistic naming engine)

Phase 3: Execution & State
├── Step 11: manifest.py                 (ephemeral state management)
├── Step 12: executor.py                 (safe rename execution)
└── Step 13: cli.py                      (CLI entrypoint, interactive prompts)

Phase 4: Polish
├── Step 14: Tests                       (unit + integration)
├── Step 15: pyproject.toml + packaging  (pip installable)
└── Step 16: README.md                   (user documentation)
```

### Phase 1 Rationale

Start with `models.py` because every other module imports from it. `constants.py` defines format maps that `discovery.py` and `preprocessing.py` need. `validator.py` is a pure function with no dependencies: it can be fully tested in isolation. `config.py` is needed by everything but depends on nothing.

### Phase 2 Rationale

Pipeline stages are implemented in data flow order. Each stage can be tested with mock inputs from the previous stage. `analyzer.py` and `namer.py` can be tested with recorded Gemini responses.

### Phase 3 Rationale

`manifest.py` and `executor.py` are the most safety-critical modules. They are implemented AFTER the analysis pipeline is working, so that by the time we reach execution, the data flowing in is well-structured and validated. `cli.py` is last because it just wires everything together.

### Dependency-Free Testing

Each module can be tested independently:

| Module | Test Strategy |
|--------|--------------|
| `models.py` | Pydantic model validation, serialization round-trips |
| `constants.py` | Format maps are correct, naming rules are consistent |
| `config.py` | YAML parsing, env var resolution, precedence rules |
| `validator.py` | All naming rules from PRD Section 8, edge cases |
| `discovery.py` | Fixture directories with known file structures |
| `metadata.py` | Fixture files with known metadata |
| `preprocessing.py` | Mock conversion tools, verify temp file handling |
| `context.py` | Fixture directory trees, breadcrumb generation |
| `analyzer.py` | Mock Gemini responses, batch size calculations |
| `namer.py` | Mock Gemini responses, strategy selection |
| `manifest.py` | Create, update, flush, load, cleanup lifecycle |
| `executor.py` | Fixture files, rename verification, crash simulation |
| `cli.py` | Click testing utilities, end-to-end with mocks |

---

*End of Architecture Design: v1.0.0*
