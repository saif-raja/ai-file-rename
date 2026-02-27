"""
Content analyzer for ai-file-rename.

Sends files to Gemini for content analysis — the first of two LLM calls.
Handles batching, file uploads, and structured JSON responses.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from ai_file_rename.config import Config
from ai_file_rename.constants import API_LIMITS, CONTENT_ANALYSIS_PROMPT
from ai_file_rename.metadata import _format_size
from ai_file_rename.models import (
    AnalyzedFile,
    ContentSummary,
    EnrichedFile,
    FileCategory,
    FolderContext,
)


def _content_summary_schema() -> dict:
    """Generate a JSON schema for the ContentSummary response.

    Uses Pydantic's model_json_schema() to produce a standard JSON schema
    dict that is passed to Gemini's response_json_schema parameter.
    """
    schema = ContentSummary.model_json_schema()
    # Remove Pydantic metadata keys that Gemini doesn't need
    schema.pop("$defs", None)
    schema.pop("description", None)
    return schema


# Cache the schema since it never changes at runtime
_CONTENT_SUMMARY_SCHEMA = _content_summary_schema()


def _extract_token_counts(response) -> dict:
    """Extract token usage from a Gemini response, falling back to 0."""
    try:
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            return {
                "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
            }
    except Exception:
        pass
    return {"input_tokens": 0, "output_tokens": 0}


def _add_token_counts(a: dict, b: dict) -> dict:
    """Sum two token count dicts."""
    return {
        "input_tokens": a.get("input_tokens", 0) + b.get("input_tokens", 0),
        "output_tokens": a.get("output_tokens", 0) + b.get("output_tokens", 0),
    }


def _format_metadata_for_prompt(enriched: EnrichedFile) -> str:
    """Format metadata as a concise context block for the Gemini prompt."""
    meta = enriched.metadata
    context = {}

    if meta.title:
        context["title"] = meta.title
    if meta.author:
        context["author"] = meta.author
    if meta.created_at:
        context["created"] = meta.created_at.strftime("%Y-%m-%d")
    if meta.modified_at:
        context["modified"] = meta.modified_at.strftime("%Y-%m-%d")
    if meta.page_count:
        context["pages"] = meta.page_count
    if meta.word_count:
        context["words"] = meta.word_count
    if meta.slide_count:
        context["slides"] = meta.slide_count
    if meta.duration_seconds:
        mins = int(meta.duration_seconds // 60)
        secs = int(meta.duration_seconds % 60)
        context["duration"] = f"{mins}m{secs:02d}s"
    if meta.dimensions:
        context["dimensions"] = meta.dimensions
    if meta.camera_model:
        camera = meta.camera_model
        if meta.camera_make:
            camera = f"{meta.camera_make} {camera}"
        context["camera"] = camera
    if meta.gps_location:
        context["location"] = meta.gps_location
    if meta.artist:
        context["artist"] = meta.artist
    if meta.album:
        context["album"] = meta.album
    if meta.sheet_names:
        context["sheets"] = meta.sheet_names

    if not context:
        return "null"

    return json.dumps(context, indent=2)


def _build_analysis_prompt(enriched: EnrichedFile, folder_context: FolderContext) -> str:
    """Build the content analysis prompt for a single file."""
    entry = enriched.entry
    meta = enriched.metadata

    return CONTENT_ANALYSIS_PROMPT.format(
        full_path=str(entry.path),
        parent_folder_name=folder_context.folder_name,
        breadcrumb_path=folder_context.breadcrumb,
        current_filename=entry.name,
        mime_type=entry.mime_type or "unknown",
        file_size_human_readable=meta.size_human,
        created_date=str(meta.created_at or "unknown"),
        modified_date=str(meta.modified_at or "unknown"),
        accessed_date=str(meta.accessed_at or "unknown"),
        is_symlink=str(entry.is_symlink),
        symlink_target=str(entry.symlink_target or "N/A"),
        embedded_metadata_json=_format_metadata_for_prompt(enriched),
    )


def _read_text_content(file_path: Path, max_bytes: int = 50_000) -> Optional[str]:
    """Read text content for text-extractable files."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_bytes)
        return content
    except Exception:
        return None


def _parse_content_summary(response_text: str) -> ContentSummary:
    """Parse a ContentSummary from Gemini's JSON response.

    Returns (summary, needs_retry) where needs_retry is True when the
    response was not valid JSON and should be retried before accepting
    the regex-fallback result.
    """
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        # Try to extract JSON from the response via regex
        import re
        match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return ContentSummary(
                    content_type="unknown",
                    primary_subject="Content analysis failed — could not parse response.",
                    key_entities=[],
                    date_references=[],
                    language="unknown",
                    confidence=0.0,
                )
        else:
            return ContentSummary(
                content_type="unknown",
                primary_subject="Content analysis failed — could not parse response.",
                key_entities=[],
                date_references=[],
                language="unknown",
                confidence=0.0,
            )

    return ContentSummary(
        content_type=data.get("content_type", "unknown"),
        primary_subject=data.get("primary_subject", "No description available."),
        key_entities=data.get("key_entities", []),
        date_references=data.get("date_references", []),
        language=data.get("language", "unknown"),
        confidence=float(data.get("confidence", 0.5)),
    )


def create_batches(
    files: list[EnrichedFile],
    max_batch_bytes: int = 80_000_000,
) -> list[list[EnrichedFile]]:
    """
    Group files into batches that fit within the Gemini request size limit.

    Strategy:
    1. Sort files by size ascending.
    2. Greedily add files to current batch until size limit is approached.
    3. Start a new batch.

    Text-extractable files are batched separately (no upload needed).
    """
    # Separate uploadable files from text-extractable
    uploadable = []
    text_files = []

    for f in files:
        if f.entry.category == FileCategory.TEXT_EXTRACTABLE:
            text_files.append(f)
        else:
            uploadable.append(f)

    # Sort by size ascending
    uploadable.sort(key=lambda f: f.metadata.size_bytes)
    text_files.sort(key=lambda f: f.metadata.size_bytes)

    batches = []

    # Batch uploadable files
    current_batch: list[EnrichedFile] = []
    current_size = 0

    for f in uploadable:
        if current_size + f.metadata.size_bytes > max_batch_bytes and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_size = 0

        current_batch.append(f)
        current_size += f.metadata.size_bytes

    if current_batch:
        batches.append(current_batch)

    # Batch text files (by count, ~20 per batch)
    for i in range(0, len(text_files), 20):
        batches.append(text_files[i : i + 20])

    return batches


def _get_mtime(path: Path) -> float:
    """Get file modification time, returning 0 on error."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


async def _analyze_single_file(
    enriched: EnrichedFile,
    folder_context: FolderContext,
    client,
    model: str,
    logger=None,
) -> tuple[AnalyzedFile, dict]:
    """Analyze a single file using Gemini. Returns (AnalyzedFile, token_counts)."""
    file_path = enriched.entry.path

    # Record mtime before analysis to detect concurrent modifications
    mtime_before = _get_mtime(file_path)

    prompt = _build_analysis_prompt(enriched, folder_context)

    contents = [prompt]

    # For text files, include content inline
    if enriched.entry.category == FileCategory.TEXT_EXTRACTABLE:
        text_content = _read_text_content(enriched.entry.path)
        if text_content:
            contents.append(f"\n\n--- FILE CONTENT ---\n{text_content}\n--- END CONTENT ---")
    elif enriched.processed_path and enriched.processed_path.exists():
        # Upload the file (or its converted version)
        uploaded = client.files.upload(file=enriched.processed_path)

        # Wait for processing if needed
        while hasattr(uploaded, "state") and uploaded.state == "PROCESSING":
            await asyncio.sleep(2)
            uploaded = client.files.get(name=uploaded.name)

        contents.append(uploaded)

    token_counts = {"input_tokens": 0, "output_tokens": 0}

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": _CONTENT_SUMMARY_SCHEMA,
            },
        )

        # Check if file was modified during analysis
        mtime_after = _get_mtime(file_path)
        if mtime_before > 0 and mtime_after > 0 and mtime_after != mtime_before:
            summary = ContentSummary(
                content_type="skipped",
                primary_subject="File modified during processing — skipped for safety.",
                key_entities=[],
                date_references=[],
                language="unknown",
                confidence=0.0,
            )
            return AnalyzedFile(enriched=enriched, summary=summary), token_counts

        token_counts = _extract_token_counts(response)

        # Retry once if Gemini returned invalid JSON
        try:
            json.loads(response.text)
        except (json.JSONDecodeError, TypeError):
            # One retry before falling back to regex parsing
            retry_response = client.models.generate_content(
                model=model,
                contents=contents,
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": _CONTENT_SUMMARY_SCHEMA,
                },
            )
            token_counts = _add_token_counts(
                token_counts, _extract_token_counts(retry_response)
            )
            response = retry_response

        summary = _parse_content_summary(response.text)

        if logger:
            logger.info(
                f"  [analyzed] {enriched.entry.name} — "
                f"type: {summary.content_type}, "
                f"confidence: {summary.confidence:.2f}, "
                f"subject: {summary.primary_subject[:60]}"
            )
    except Exception as e:
        summary = ContentSummary(
            content_type="unknown",
            primary_subject=f"Analysis failed: {str(e)[:100]}",
            key_entities=[],
            date_references=[],
            language="unknown",
            confidence=0.0,
        )
        if logger:
            logger.warning(
                f"  [FAILED] {enriched.entry.name} — {str(e)[:100]}"
            )

    return AnalyzedFile(enriched=enriched, summary=summary), token_counts


async def _retry_with_backoff(coro_factory, max_retries: int = 5) -> object:
    """Execute an async function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + (time.time() % 1)  # jitter
            await asyncio.sleep(wait)


async def analyze_folder(
    folder: FolderContext,
    client,
    model: str,
    config: Config,
    logger=None,
) -> tuple[list[AnalyzedFile], dict]:
    """
    Analyze all files in a folder using Gemini.

    Files are processed individually (batching is done at the folder level
    for parallelism). Each file gets a structured content summary.

    Args:
        folder: The folder context with files to analyze.
        client: The Gemini client (google.genai.Client).
        model: Model name to use.
        config: Resolved configuration.

    Returns:
        Tuple of (list of AnalyzedFile objects, token_counts dict).
    """
    results = []
    total_tokens = {"input_tokens": 0, "output_tokens": 0}

    for enriched in folder.files:
        if enriched.entry.skip_reason:
            # Skip files with known issues
            results.append(
                AnalyzedFile(
                    enriched=enriched,
                    summary=ContentSummary(
                        content_type="skipped",
                        primary_subject=enriched.entry.skip_reason,
                        key_entities=[],
                        date_references=[],
                        language="unknown",
                        confidence=0.0,
                    ),
                )
            )
            continue

        try:
            result = await _retry_with_backoff(
                lambda e=enriched: _analyze_single_file(e, folder, client, model, logger=logger)
            )
            analyzed, file_tokens = result
            results.append(analyzed)
            total_tokens = _add_token_counts(total_tokens, file_tokens)
        except Exception as e:
            # Non-fatal: skip file with warning
            results.append(
                AnalyzedFile(
                    enriched=enriched,
                    summary=ContentSummary(
                        content_type="error",
                        primary_subject=f"Analysis failed after retries: {str(e)[:100]}",
                        key_entities=[],
                        date_references=[],
                        language="unknown",
                        confidence=0.0,
                    ),
                )
            )

    return results, total_tokens


async def analyze_all(
    folders: dict[Path, FolderContext],
    client,
    model: str,
    config: Config,
    concurrency: int = 3,
    logger=None,
) -> tuple[dict[Path, list[AnalyzedFile]], dict]:
    """
    Analyze all folders concurrently (within concurrency limit).

    Args:
        folders: Dict mapping folder paths to FolderContext objects.
        client: The Gemini client.
        model: Model name to use.
        config: Resolved configuration.
        concurrency: Maximum concurrent API calls.

    Returns:
        Tuple of (dict mapping folder paths to lists of AnalyzedFile objects,
        token_counts dict with total input/output tokens).
    """
    semaphore = asyncio.Semaphore(concurrency)
    results: dict[Path, list[AnalyzedFile]] = {}
    all_tokens = {"input_tokens": 0, "output_tokens": 0}

    async def process_folder(folder_path: Path, folder: FolderContext):
        nonlocal all_tokens
        async with semaphore:
            analyzed, folder_tokens = await analyze_folder(folder, client, model, config, logger=logger)
            results[folder_path] = analyzed
            all_tokens = _add_token_counts(all_tokens, folder_tokens)

    tasks = [
        process_folder(path, folder)
        for path, folder in folders.items()
    ]

    await asyncio.gather(*tasks)
    return results, all_tokens
