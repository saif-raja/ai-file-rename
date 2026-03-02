"""
Constants for the AI File Rename tool.

This module defines all constants used across the pipeline:
- FORMAT_CATEGORIES: Maps file extensions to processing categories.
- MIME_TYPE_MAP: Maps extensions to MIME types for Gemini uploads.
- NAMING_RULES: Cross-platform naming constraints.
- CONTENT_ANALYSIS_PROMPT: Prompt template for per-file Gemini content analysis.
- HOLISTIC_NAMING_PROMPT: Prompt template for per-folder holistic naming.
- API_LIMITS: Gemini File API and request limits.
- COST_PER_TOKEN: Approximate token costs per Gemini model.

All prompt templates use {placeholder} syntax compatible with ``str.format()``
or ``str.format_map()``.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# 1. FORMAT_CATEGORIES
# ---------------------------------------------------------------------------
# Maps lowercase file extensions (without leading dot) to a FileCategory value.
# Values correspond to the FileCategory enum defined in models.py.
# ---------------------------------------------------------------------------

FORMAT_CATEGORIES: Final[dict[str, str]] = {
    # --- Tier 1: Directly Processable (Gemini native) ---
    "jpeg": "directly_processable",
    "jpg": "directly_processable",
    "png": "directly_processable",
    "webp": "directly_processable",
    "heic": "directly_processable",
    "heif": "directly_processable",
    "pdf": "directly_processable",
    "mp3": "directly_processable",
    "wav": "directly_processable",
    "aac": "directly_processable",
    "ogg": "directly_processable",
    "flac": "directly_processable",
    "aiff": "directly_processable",
    "mp4": "directly_processable",
    "mov": "directly_processable",
    "avi": "directly_processable",
    "webm": "directly_processable",
    "wmv": "directly_processable",
    "mkv": "directly_processable",
    "flv": "directly_processable",
    # --- Tier 2: Convertible (requires pre-processing) ---
    "svg": "convertible",
    "gif": "convertible",
    "bmp": "convertible",
    "tiff": "convertible",
    "tif": "convertible",
    "docx": "convertible",
    "pptx": "convertible",
    "xlsx": "convertible",
    "doc": "convertible",
    "ppt": "convertible",
    "xls": "convertible",
    # --- Tier 3: Text-Extractable ---
    "txt": "text_extractable",
    "md": "text_extractable",
    "html": "text_extractable",
    "xml": "text_extractable",
    "json": "text_extractable",
    "yaml": "text_extractable",
    "yml": "text_extractable",
    "csv": "text_extractable",
    "tsv": "text_extractable",
    "py": "text_extractable",
    "js": "text_extractable",
    "ts": "text_extractable",
    "rs": "text_extractable",
    "go": "text_extractable",
    "java": "text_extractable",
    "c": "text_extractable",
    "cpp": "text_extractable",
    "h": "text_extractable",
    "hpp": "text_extractable",
    "rb": "text_extractable",
    "php": "text_extractable",
    "sh": "text_extractable",
    "bash": "text_extractable",
    "zsh": "text_extractable",
    "log": "text_extractable",
    "ini": "text_extractable",
    "toml": "text_extractable",
    "cfg": "text_extractable",
    "conf": "text_extractable",
    "env": "text_extractable",
    "sql": "text_extractable",
    "r": "text_extractable",
    "swift": "text_extractable",
    "kt": "text_extractable",
    "scala": "text_extractable",
    "lua": "text_extractable",
    "pl": "text_extractable",
    "pm": "text_extractable",
    # --- Tier 4: Unsupported (skipped with warning) ---
    "zip": "unsupported",
    "tar": "unsupported",
    "gz": "unsupported",
    "rar": "unsupported",
    "7z": "unsupported",
    "exe": "unsupported",
    "app": "unsupported",
    "dmg": "unsupported",
    "msi": "unsupported",
    "deb": "unsupported",
    "rpm": "unsupported",
    "iso": "unsupported",
    "img": "unsupported",
    "db": "unsupported",
    "sqlite": "unsupported",
    "mdb": "unsupported",
    "dll": "unsupported",
    "so": "unsupported",
    "dylib": "unsupported",
    "sys": "unsupported",
    "psd": "unsupported",
    "ai": "unsupported",
    "sketch": "unsupported",
    "fig": "unsupported",
    "ttf": "unsupported",
    "otf": "unsupported",
    "woff": "unsupported",
    "woff2": "unsupported",
    "obj": "unsupported",
    "stl": "unsupported",
    "fbx": "unsupported",
    "blend": "unsupported",
}

# ---------------------------------------------------------------------------
# 2. MIME_TYPE_MAP
# ---------------------------------------------------------------------------
# Maps lowercase file extensions to their MIME type strings.  Used when
# uploading files to the Gemini File API.
# ---------------------------------------------------------------------------

MIME_TYPE_MAP: Final[dict[str, str]] = {
    # Images
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "heic": "image/heic",
    "heif": "image/heif",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "svg": "image/svg+xml",
    # Documents
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    # Audio
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "aac": "audio/aac",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
    "aiff": "audio/aiff",
    # Video
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "avi": "video/x-msvideo",
    "webm": "video/webm",
    "wmv": "video/x-ms-wmv",
    "mkv": "video/x-matroska",
    "flv": "video/x-flv",
    # Text / Code
    "txt": "text/plain",
    "md": "text/markdown",
    "html": "text/html",
    "xml": "text/xml",
    "json": "application/json",
    "yaml": "application/x-yaml",
    "yml": "application/x-yaml",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "py": "text/x-python",
    "js": "text/javascript",
    "ts": "text/typescript",
    "rs": "text/x-rust",
    "go": "text/x-go",
    "java": "text/x-java",
    "c": "text/x-c",
    "cpp": "text/x-c++",
    "h": "text/x-c",
    "hpp": "text/x-c++",
    "rb": "text/x-ruby",
    "php": "text/x-php",
    "sh": "text/x-shellscript",
    "bash": "text/x-shellscript",
    "zsh": "text/x-shellscript",
    "log": "text/plain",
    "ini": "text/plain",
    "toml": "text/plain",
    "cfg": "text/plain",
    "conf": "text/plain",
    "env": "text/plain",
    "sql": "text/x-sql",
    "r": "text/x-r",
    "swift": "text/x-swift",
    "kt": "text/x-kotlin",
    "scala": "text/x-scala",
    "lua": "text/x-lua",
    "pl": "text/x-perl",
    "pm": "text/x-perl",
}

# ---------------------------------------------------------------------------
# 3. CONVERSION_MAP
# ---------------------------------------------------------------------------
# 3. NAMING_RULES
# ---------------------------------------------------------------------------
# Cross-platform file-naming constraints.  These are the intersection of the
# most restrictive rules across Windows, macOS, and Linux so that a file
# renamed on any platform will be valid on all three.
# ---------------------------------------------------------------------------

NAMING_RULES: Final[dict[str, object]] = {
    # Maximum total file name length including extension (chars).
    # Windows MAX_PATH is 260; 200 leaves room for the directory portion.
    "max_name_length": 200,
    # Minimum number of hyphen-separated words in the generated stem.
    "min_words": 2,
    # Maximum number of hyphen-separated words in the generated stem.
    "max_words": 8,
    # Word separator used in generated names.
    "separator": "-",
    # Regex pattern matching characters forbidden in file names on any OS.
    # Covers: < > : " / \ | ? * and control characters \x00-\x1f
    "forbidden_chars_pattern": r'[<>:"/\\|?*\x00-\x1f]',
    # Windows reserved device names (case-insensitive).
    "windows_reserved_names": frozenset({
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }),
    # Fallback name when no meaningful name can be generated.
    "default_name": "unnamed-file",
}

# ---------------------------------------------------------------------------
# 5. CONTENT_ANALYSIS_PROMPT
# ---------------------------------------------------------------------------
# Prompt template sent to Gemini for per-file content analysis (Step 3 of
# the pipeline).  The structured JSON response is parsed into a
# ContentSummary model.
#
# Placeholders injected by analyzer.py:
#   {full_path}               - Absolute path to the file
#   {parent_folder_name}      - Immediate parent directory name
#   {breadcrumb_path}         - Folder hierarchy e.g. "docs > research > ml"
#   {current_filename}        - Current file name including extension
#   {mime_type}               - MIME type string
#   {file_size_human_readable}- Human-readable size e.g. "4.2 MB"
#   {created_date}            - File system birth/creation time (ISO 8601)
#   {modified_date}           - File system modification time (ISO 8601)
#   {accessed_date}           - File system access time (ISO 8601)
#   {is_symlink}              - "true" or "false"
#   {symlink_target}          - Resolved symlink target path, or "N/A"
#   {embedded_metadata_json}  - JSON string of extracted metadata, or "null"
# ---------------------------------------------------------------------------

CONTENT_ANALYSIS_PROMPT: Final[str] = """\
You are a file content analyzer. Your job is to produce a brief, \
factual summary of this file's content that will be used to generate \
a descriptive filename.

Context:
- This file is located at: {full_path}
- Parent folder: {parent_folder_name}
- Folder hierarchy: {breadcrumb_path}
- Current filename: {current_filename}
- File type: {mime_type}
- File size: {file_size_human_readable}
- Created date: {created_date}
- Last modified: {modified_date}
- Last accessed: {accessed_date}
- Is symlink: {is_symlink}
- Symlink target: {symlink_target}
- Embedded metadata:
  {embedded_metadata_json}

Instructions:
- Describe the PRIMARY content/subject of this file in 2-3 sentences.
- Identify the TYPE of content (e.g., "photograph of...", \
"presentation about...", "invoice from...", "research paper on...").
- Extract any key identifiers: dates, names, organizations, topics.
- Use the embedded metadata to enrich your understanding. For example: \
an author name, a document title, a camera location, or a creation \
date can all provide important context for naming.
- The file system dates and size are supplementary signals. A very \
large file may contain more substantial content. Creation dates \
may indicate when the content is from (though they can also reflect \
when the file was copied). Use these as hints, not as primary naming \
sources.
- Do NOT suggest a filename. Just describe the content.

Respond in this exact JSON format:
{{
  "content_type": "photograph | document | presentation | spreadsheet | audio | video | diagram | screenshot | ...",
  "primary_subject": "brief description of the main subject",
  "key_entities": ["entity1", "entity2"],
  "date_references": ["YYYY-MM-DD or partial dates found in content OR metadata"],
  "language": "en | es | fr | ...",
  "confidence": 0.0-1.0
}}
"""

# ---------------------------------------------------------------------------
# 7. HOLISTIC_NAMING_PROMPT
# ---------------------------------------------------------------------------
# Prompt template sent to Gemini for per-folder holistic naming (Step 4).
# All files in a single folder are named together so that names are
# contextually differentiated and complementary.
#
# Placeholders injected by namer.py:
#   {full_folder_path}   - Absolute path to the folder
#   {breadcrumb_path}    - Folder hierarchy breadcrumb
#   {folder_name}        - Immediate folder name
#   {file_count}         - Total number of files being named
#   {file_summaries}     - Pre-formatted block of per-file summaries
#   {naming_rules}       - Pre-formatted block of naming rules
#   {custom_instructions}- User-supplied extra instructions, or empty string
# ---------------------------------------------------------------------------

HOLISTIC_NAMING_PROMPT: Final[str] = """\
You are a file naming specialist. You are renaming ALL files in a \
single folder as a cohesive set. Each name must be unique, descriptive, \
and complementary to the others.

FOLDER CONTEXT:
- Folder path: {full_folder_path}
- Folder hierarchy: {breadcrumb_path}
- Folder name: {folder_name}
- Total files in folder: {file_count}

FILE SUMMARIES:
{file_summaries}

NAMING RULES:
{naming_rules}

INSTRUCTIONS:
1. Consider all files as a SET. Each name should occupy a distinct \
semantic niche within the folder's context.
2. Use the folder hierarchy as implicit context -- do not repeat folder \
name information in file names. If the folder is "invoices-2023", \
do not name files "invoice-january-2023.pdf". Just "january.pdf" \
or "january-acme-corp.pdf" is sufficient.
3. If files form a natural sequence (chapters, months, versions), \
use consistent naming with sequence indicators.
4. Ensure NO two files get the same name.
5. If the current file name is already descriptive and accurate, \
you may keep it (return it unchanged).
6. Generated names must be:
   - Lowercase only.
   - 2-8 hyphen-separated words describing the content.
   - Noun-phrase oriented (not sentences or sentence fragments).
   - Ordered by specificity: most unique descriptor first, most general last.
   - ASCII only (transliterate non-ASCII characters).
   - The original file extension must be preserved exactly.
   - NEVER start with articles like "a", "the", "this", or verbs \
like "describes", "outlines", "contains". Lead with the most \
distinctive noun or proper noun.
7. Do NOT include the folder name or path components in the file name \
unless absolutely necessary for disambiguation.

EXAMPLES of good naming:
- IMG_001.jpg (photo of sunset at Golden Gate Bridge) -> sunset-golden-gate-bridge.jpg
- document.pdf (Acme Corp Q3 2023 revenue report) -> acme-corp-q3-revenue-report.pdf
- notes.txt (ML research on transformer attention) -> transformer-attention-research-notes.txt
- recording.mp3 (interview with Dr. Sarah Chen) -> sarah-chen-interview-recording.mp3
- Screenshot 2023-11-15.png (error dialog in settings page) -> settings-page-error-dialog.png

BAD naming patterns to avoid:
- "a-photo-of-the-sunset.jpg" (starts with article, too verbose)
- "this-document-outlines-the-architecture.pdf" (sentence fragment)
- "file-containing-budget-data.csv" (starts with "file")
- "notes-about-machine-learning.txt" ("about" is filler)
{custom_instructions}

Respond in this exact JSON format:
{{
  "folder_context_summary": "brief description of what this folder contains",
  "naming_strategy": "brief description of naming approach chosen",
  "renames": [
    {{
      "current_name": "original_filename.ext",
      "proposed_name": "new-descriptive-name.ext",
      "reasoning": "why this name was chosen",
      "confidence": 0.0-1.0
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# 8. API_LIMITS
# ---------------------------------------------------------------------------
# Gemini File API and request constraints.
# ---------------------------------------------------------------------------

API_LIMITS: Final[dict[str, int | float]] = {
    # Maximum single file size accepted by Gemini File API (2 GB).
    "max_file_size_bytes": 2 * 1024**3,
    # Maximum request payload size (100 MB).
    "max_request_size_bytes": 100 * 1024**2,
    # Safety margin for batching -- stay below the hard request limit (80 MB).
    "max_batch_size_bytes": 80 * 1024**2,
    # Maximum number of pages Gemini will process in a single PDF.
    "pdf_page_limit": 1000,
    # Maximum retry attempts for transient API errors.
    "max_retries": 5,
    # Base delay in seconds for exponential backoff.
    "base_retry_delay": 1.0,
}

# ---------------------------------------------------------------------------
# 9. COST_PER_TOKEN
# ---------------------------------------------------------------------------
# Approximate per-token costs (in USD) for supported Gemini models.
# Values are best-effort estimates as of 2026-02; actual billing may differ.
# Each entry maps a model identifier to {"input": <cost>, "output": <cost>}.
# ---------------------------------------------------------------------------

COST_PER_TOKEN: Final[dict[str, dict[str, float]]] = {
    "gemini-2.0-flash": {
        "input": 0.000_000_10,   # $0.10 per 1M input tokens
        "output": 0.000_000_40,  # $0.40 per 1M output tokens
    },
    "gemini-2.5-flash": {
        "input": 0.000_000_15,   # $0.15 per 1M input tokens
        "output": 0.000_000_60,  # $0.60 per 1M output tokens
    },
    "gemini-2.5-pro": {
        "input": 0.000_001_25,   # $1.25 per 1M input tokens
        "output": 0.000_005_00,  # $5.00 per 1M output tokens
    },
}
