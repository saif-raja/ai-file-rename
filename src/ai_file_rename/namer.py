"""
Holistic naming engine for ai-file-rename.

Generates names for ALL files in a folder as a cohort — the second of two LLM calls.
Uses a strategy pattern for scaling to different folder sizes.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Protocol

from ai_file_rename.config import Config
from ai_file_rename.constants import HOLISTIC_NAMING_PROMPT, NAMING_RULES
from ai_file_rename.models import (
    AnalyzedFile,
    ContentSummary,
    FolderContext,
    ProposedRename,
)


def _naming_response_schema() -> dict:
    """Generate a JSON schema for the holistic naming response.

    The naming endpoint returns:
    { "renames": [ { "current_name": str, "proposed_name": str,
                     "reasoning": str, "confidence": float } ] }
    """
    return {
        "type": "object",
        "properties": {
            "renames": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "current_name": {"type": "string"},
                        "proposed_name": {"type": "string"},
                        "reasoning": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["current_name", "proposed_name", "reasoning", "confidence"],
                },
            },
        },
        "required": ["renames"],
    }


# Cache the schema since it never changes at runtime
_NAMING_RESPONSE_SCHEMA = _naming_response_schema()


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


def _format_naming_rules(config: Config) -> str:
    """Format naming rules as a text block for the prompt."""
    rules = [
        f"- Lowercase, {config.separator}-separated, {config.min_words}-{config.max_words} words",
        "- ASCII only, no forbidden characters: < > : \" / \\ | ? *",
        "- No trailing dots or spaces",
        f"- No Windows reserved names: CON, PRN, AUX, NUL, COM1-9, LPT1-9",
        f"- Maximum {NAMING_RULES['max_name_length']} characters including extension",
        "- Extension is NEVER changed (only the stem is renamed)",
        "- Each name must be unique within the folder",
        "- Names should be noun-phrase oriented, not sentences",
        "- If the current name is already descriptive, keep it unchanged",
    ]
    return "\n".join(rules)


def _format_file_summary(analyzed: AnalyzedFile, index: int) -> str:
    """Format a single file's summary for the naming prompt."""
    entry = analyzed.enriched.entry
    meta = analyzed.enriched.metadata
    summary = analyzed.summary

    lines = [
        f"File {index + 1}:",
        f"  Current name: {entry.name}",
        f"  Type: {summary.content_type}",
        f"  Size: {meta.size_human}",
    ]

    if meta.created_at:
        lines.append(f"  Created: {meta.created_at.strftime('%Y-%m-%d')}")
    if meta.modified_at:
        lines.append(f"  Modified: {meta.modified_at.strftime('%Y-%m-%d')}")

    # Add metadata context
    meta_parts = []
    if meta.title:
        meta_parts.append(f"title: \"{meta.title}\"")
    if meta.author:
        meta_parts.append(f"author: \"{meta.author}\"")
    if meta.page_count:
        meta_parts.append(f"pages: {meta.page_count}")
    if meta.dimensions:
        meta_parts.append(f"dimensions: {meta.dimensions}")
    if meta.duration_seconds:
        mins = int(meta.duration_seconds // 60)
        secs = int(meta.duration_seconds % 60)
        meta_parts.append(f"duration: {mins}m{secs:02d}s")

    if meta_parts:
        lines.append(f"  Metadata: {{{', '.join(meta_parts)}}}")

    lines.append(f"  Summary: {summary.primary_subject}")

    if summary.key_entities:
        lines.append(f"  Key entities: {summary.key_entities}")
    if summary.date_references:
        lines.append(f"  Dates: {summary.date_references}")

    return "\n".join(lines)


def _parse_naming_response(
    response_text: str,
    files: list[AnalyzedFile],
    folder_path: Path,
    logger=None,
) -> list[ProposedRename]:
    """Parse the naming response from Gemini into ProposedRename objects."""
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"Could not parse naming response as JSON")

    renames_data = data.get("renames", [])

    # Build a lookup from current name to AnalyzedFile
    file_lookup = {f.enriched.entry.name: f for f in files}
    input_names = set(file_lookup.keys())
    matched_names = set()

    results = []
    for rename_data in renames_data:
        current_name = rename_data.get("current_name", "")
        proposed_name = rename_data.get("proposed_name", current_name)
        reasoning = rename_data.get("reasoning", "")
        confidence = float(rename_data.get("confidence", 0.5))

        if logger:
            logger.debug(
                f"  [parse] {current_name} -> {proposed_name} "
                f"(confidence: {confidence:.2f}, reasoning: {reasoning[:80]})"
            )

        # Find the matching file
        file_entry = file_lookup.get(current_name)
        if file_entry is None:
            # Try case-insensitive match
            for name, entry in file_lookup.items():
                if name.lower() == current_name.lower():
                    file_entry = entry
                    current_name = name  # use the actual name for tracking
                    break

        if file_entry is None:
            if logger:
                logger.warning(
                    f"  [naming-miss] {current_name} — "
                    f"present in Gemini response but not in input set"
                )
            continue

        matched_names.add(current_name)

        current_path = file_entry.enriched.entry.path
        proposed_path = current_path.parent / proposed_name

        results.append(
            ProposedRename(
                current_name=current_name,
                proposed_name=proposed_name,
                current_path=current_path,
                proposed_path=proposed_path,
                reasoning=reasoning,
                confidence=confidence,
                is_unchanged=(current_name == proposed_name),
            )
        )

    # Warn about files in the input set that were not in the response
    if logger:
        missing = input_names - matched_names
        for name in missing:
            logger.warning(
                f"  [naming-miss] {name} — "
                f"not found in Gemini response, will not be renamed"
            )

    return results


# --- Strategy Pattern ---


class NamingStrategy(Protocol):
    """Protocol for naming strategies."""

    async def generate_names(
        self,
        files: list[AnalyzedFile],
        context: FolderContext,
        client,
        model: str,
        config: Config,
    ) -> tuple[list[ProposedRename], dict]:
        ...


class FullHolisticStrategy:
    """For folders with 1-50 files. Single LLM call."""

    async def generate_names(
        self,
        files: list[AnalyzedFile],
        context: FolderContext,
        client,
        model: str,
        config: Config,
        logger=None,
    ) -> tuple[list[ProposedRename], dict]:
        # Build file summaries
        summaries = "\n\n".join(
            _format_file_summary(f, i) for i, f in enumerate(files)
        )

        custom = ""
        if config.custom_instructions:
            custom = f"\n\nADDITIONAL INSTRUCTIONS:\n{config.custom_instructions}"

        prompt = HOLISTIC_NAMING_PROMPT.format(
            full_folder_path=str(context.folder_path),
            breadcrumb_path=context.breadcrumb,
            folder_name=context.folder_name,
            file_count=len(files),
            file_summaries=summaries,
            naming_rules=_format_naming_rules(config),
            custom_instructions=custom,
        )

        if logger:
            logger.debug(
                f"  [naming-prompt] FullHolistic: {len(files)} files, "
                f"prompt length: {len(prompt)} chars, folder: {context.folder_name}"
            )

        response = client.models.generate_content(
            model=model,
            contents=[prompt],
            config={
                "response_mime_type": "application/json",
                "response_json_schema": _NAMING_RESPONSE_SCHEMA,
            },
        )

        token_counts = _extract_token_counts(response)

        renames = _parse_naming_response(
            response.text, files, context.folder_path, logger=logger
        )

        if logger:
            for r in renames:
                tag = "unchanged" if r.is_unchanged else "named"
                logger.info(
                    f"  [{tag}] {r.current_name} -> {r.proposed_name} "
                    f"(confidence: {r.confidence:.2f})"
                )

        return renames, token_counts


class ClusteredHolisticStrategy:
    """For folders with 51-200 files. Cluster by content type, then name each cluster."""

    async def generate_names(
        self,
        files: list[AnalyzedFile],
        context: FolderContext,
        client,
        model: str,
        config: Config,
        logger=None,
    ) -> tuple[list[ProposedRename], dict]:
        # Cluster by content type
        clusters: dict[str, list[AnalyzedFile]] = {}
        for f in files:
            ct = f.summary.content_type
            if ct not in clusters:
                clusters[ct] = []
            clusters[ct].append(f)

        # Build overview
        overview_parts = []
        for ct, cluster_files in clusters.items():
            overview_parts.append(f"- {ct}: {len(cluster_files)} files")
        overview = "\n".join(overview_parts)

        if logger:
            logger.debug(
                f"  [naming-prompt] Clustered: {len(files)} files in "
                f"{len(clusters)} clusters, folder: {context.folder_name}"
            )

        all_renames = []
        prior_names = []
        total_tokens = {"input_tokens": 0, "output_tokens": 0}

        for ct, cluster_files in clusters.items():
            # Sub-batch if cluster > 50
            for i in range(0, len(cluster_files), 50):
                batch = cluster_files[i : i + 50]

                summaries = "\n\n".join(
                    _format_file_summary(f, j) for j, f in enumerate(batch)
                )

                prior_context = ""
                if prior_names:
                    prior_context = (
                        f"\n\nPreviously assigned names in this folder:\n"
                        + "\n".join(f"- {n}" for n in prior_names)
                    )

                custom = ""
                if config.custom_instructions:
                    custom = f"\n\nADDITIONAL INSTRUCTIONS:\n{config.custom_instructions}"

                prompt = HOLISTIC_NAMING_PROMPT.format(
                    full_folder_path=str(context.folder_path),
                    breadcrumb_path=context.breadcrumb,
                    folder_name=context.folder_name,
                    file_count=len(batch),
                    file_summaries=(
                        f"FOLDER OVERVIEW:\n{overview}\n\n"
                        f"You are naming the '{ct}' group ({len(batch)} files).{prior_context}\n\n"
                        f"FILE SUMMARIES:\n{summaries}"
                    ),
                    naming_rules=_format_naming_rules(config),
                    custom_instructions=custom,
                )

                if logger:
                    logger.debug(
                        f"  [naming-batch] cluster '{ct}' batch {i // 50 + 1}: "
                        f"{len(batch)} files, prompt: {len(prompt)} chars"
                    )

                response = client.models.generate_content(
                    model=model,
                    contents=[prompt],
                    config={"response_mime_type": "application/json", "response_json_schema": _NAMING_RESPONSE_SCHEMA},
                )

                total_tokens = _add_token_counts(total_tokens, _extract_token_counts(response))

                batch_renames = _parse_naming_response(
                    response.text, batch, context.folder_path, logger=logger
                )
                all_renames.extend(batch_renames)
                prior_names.extend(r.proposed_name for r in batch_renames)

                if logger:
                    for r in batch_renames:
                        tag = "unchanged" if r.is_unchanged else "named"
                        logger.info(
                            f"  [{tag}] {r.current_name} -> {r.proposed_name} "
                            f"(confidence: {r.confidence:.2f})"
                        )

        return all_renames, total_tokens


class SampledHolisticStrategy:
    """For folders with 201-500 files. Sample, establish patterns, then apply."""

    async def generate_names(
        self,
        files: list[AnalyzedFile],
        context: FolderContext,
        client,
        model: str,
        config: Config,
        logger=None,
    ) -> tuple[list[ProposedRename], dict]:
        # Stratified sample of ~50 files
        sample_size = min(50, len(files))
        clusters: dict[str, list[AnalyzedFile]] = {}
        for f in files:
            ct = f.summary.content_type
            if ct not in clusters:
                clusters[ct] = []
            clusters[ct].append(f)

        sample = []
        per_cluster = max(1, sample_size // len(clusters))
        for ct_files in clusters.values():
            sample.extend(ct_files[:per_cluster])
        sample = sample[:sample_size]

        if logger:
            logger.debug(
                f"  [naming-prompt] Sampled: {len(files)} files, "
                f"sample size: {len(sample)}, folder: {context.folder_name}"
            )

        # Name the sample holistically
        full_strategy = FullHolisticStrategy()
        sample_renames, total_tokens = await full_strategy.generate_names(
            sample, context, client, model, config, logger=logger
        )

        # Apply patterns to remaining files
        sample_names = {r.current_name for r in sample_renames}
        remaining = [f for f in files if f.enriched.entry.name not in sample_names]

        if not remaining:
            return sample_renames, total_tokens

        # Send remaining in batches with sample names as context
        all_renames = list(sample_renames)
        prior_names = [r.proposed_name for r in sample_renames]

        for i in range(0, len(remaining), 50):
            batch = remaining[i : i + 50]
            summaries = "\n\n".join(
                _format_file_summary(f, j) for j, f in enumerate(batch)
            )

            custom = ""
            if config.custom_instructions:
                custom = f"\n\nADDITIONAL INSTRUCTIONS:\n{config.custom_instructions}"

            prompt = HOLISTIC_NAMING_PROMPT.format(
                full_folder_path=str(context.folder_path),
                breadcrumb_path=context.breadcrumb,
                folder_name=context.folder_name,
                file_count=len(batch),
                file_summaries=(
                    f"Previously named files in this folder (follow the same style):\n"
                    + "\n".join(f"- {n}" for n in prior_names)
                    + f"\n\nNow name these additional files:\n{summaries}"
                ),
                naming_rules=_format_naming_rules(config),
                custom_instructions=custom,
            )

            response = client.models.generate_content(
                model=model,
                contents=[prompt],
                config={"response_mime_type": "application/json", "response_json_schema": _NAMING_RESPONSE_SCHEMA},
            )

            total_tokens = _add_token_counts(total_tokens, _extract_token_counts(response))

            batch_renames = _parse_naming_response(
                response.text, batch, context.folder_path, logger=logger
            )
            all_renames.extend(batch_renames)
            prior_names.extend(r.proposed_name for r in batch_renames)

            if logger:
                for r in batch_renames:
                    tag = "unchanged" if r.is_unchanged else "named"
                    logger.info(
                        f"  [{tag}] {r.current_name} -> {r.proposed_name} "
                        f"(confidence: {r.confidence:.2f})"
                    )

        return all_renames, total_tokens


class ProgressiveHolisticStrategy:
    """For folders with 500+ files. Sequential batches with accumulated context."""

    async def generate_names(
        self,
        files: list[AnalyzedFile],
        context: FolderContext,
        client,
        model: str,
        config: Config,
        logger=None,
    ) -> tuple[list[ProposedRename], dict]:
        all_renames = []
        prior_names = []
        total_tokens = {"input_tokens": 0, "output_tokens": 0}
        batch_size = 50

        if logger:
            logger.debug(
                f"  [naming-prompt] Progressive: {len(files)} files, "
                f"batch size: {batch_size}, folder: {context.folder_name}"
            )

        for i in range(0, len(files), batch_size):
            batch = files[i : i + batch_size]
            summaries = "\n\n".join(
                _format_file_summary(f, j) for j, f in enumerate(batch)
            )

            prior_context = ""
            if prior_names:
                prior_context = (
                    f"\n\nPreviously named files in this folder:\n"
                    + "\n".join(f"- {n}" for n in prior_names)
                )

            custom = ""
            if config.custom_instructions:
                custom = f"\n\nADDITIONAL INSTRUCTIONS:\n{config.custom_instructions}"

            prompt = HOLISTIC_NAMING_PROMPT.format(
                full_folder_path=str(context.folder_path),
                breadcrumb_path=context.breadcrumb,
                folder_name=context.folder_name,
                file_count=len(batch),
                file_summaries=f"{prior_context}\n\nFILE SUMMARIES:\n{summaries}",
                naming_rules=_format_naming_rules(config),
                custom_instructions=custom,
            )

            if logger:
                logger.debug(
                    f"  [naming-batch] batch {i // batch_size + 1}: "
                    f"{len(batch)} files, prompt: {len(prompt)} chars"
                )

            response = client.models.generate_content(
                model=model,
                contents=[prompt],
                config={"response_mime_type": "application/json", "response_json_schema": _NAMING_RESPONSE_SCHEMA},
            )

            total_tokens = _add_token_counts(total_tokens, _extract_token_counts(response))

            batch_renames = _parse_naming_response(
                response.text, batch, context.folder_path, logger=logger
            )
            all_renames.extend(batch_renames)
            prior_names.extend(r.proposed_name for r in batch_renames)

            if logger:
                for r in batch_renames:
                    tag = "unchanged" if r.is_unchanged else "named"
                    logger.info(
                        f"  [{tag}] {r.current_name} -> {r.proposed_name} "
                        f"(confidence: {r.confidence:.2f})"
                    )

        return all_renames, total_tokens


def _name_single_file(analyzed: AnalyzedFile, config: Config, logger=None) -> list[ProposedRename]:
    """Generate a name for a single file from its content analysis alone.

    When a folder has exactly one file, we skip the holistic naming LLM
    call entirely and derive a name from the content summary. This saves
    one API call.
    """
    import re
    import unicodedata

    entry = analyzed.enriched.entry
    summary = analyzed.summary
    extension = entry.extension

    # Build a candidate name from the primary subject
    subject = summary.primary_subject
    # Strip non-ASCII
    subject = unicodedata.normalize("NFKD", subject).encode("ascii", "ignore").decode()
    # Lowercase and replace non-alphanum with separator
    sep = config.separator
    candidate = re.sub(r"[^a-z0-9]+", sep, subject.lower()).strip(sep)
    # Enforce word count limits
    words = candidate.split(sep)
    words = words[: config.max_words]
    if len(words) < config.min_words and summary.key_entities:
        # Pad with key entities if subject is too short
        for entity in summary.key_entities:
            clean = re.sub(r"[^a-z0-9]+", sep, entity.lower()).strip(sep)
            if clean and clean not in words:
                words.append(clean)
            if len(words) >= config.min_words:
                break
    candidate = sep.join(words)

    if logger:
        logger.debug(
            f"  [single-file] subject: {subject[:60]}, "
            f"words: {words}, candidate: {candidate}"
        )

    # Ensure the name isn't empty
    if not candidate:
        candidate = f"file{sep}{summary.content_type}"

    proposed_name = f"{candidate}.{extension}" if extension else candidate

    # If the proposed name matches the current name, it's unchanged
    is_unchanged = proposed_name == entry.name

    if logger:
        tag = "unchanged" if is_unchanged else "named:single"
        logger.info(
            f"  [{tag}] {entry.name} -> {proposed_name} "
            f"(deterministic, no LLM call)"
        )

    return [
        ProposedRename(
            current_name=entry.name,
            proposed_name=proposed_name,
            current_path=entry.path,
            proposed_path=entry.path.parent / proposed_name,
            reasoning=f"Single-file folder: named from content analysis ({summary.content_type})",
            confidence=summary.confidence,
            is_unchanged=is_unchanged,
        )
    ]


def select_strategy(file_count: int) -> NamingStrategy:
    """Select the appropriate naming strategy based on file count."""
    if file_count <= 50:
        return FullHolisticStrategy()
    elif file_count <= 200:
        return ClusteredHolisticStrategy()
    elif file_count <= 500:
        return SampledHolisticStrategy()
    else:
        return ProgressiveHolisticStrategy()


async def name_folder(
    folder_path: Path,
    analyzed_files: list[AnalyzedFile],
    folder_context: FolderContext,
    client,
    model: str,
    config: Config,
    logger=None,
) -> tuple[list[ProposedRename], dict]:
    """
    Generate holistic names for all files in a single folder.

    Selects the appropriate strategy based on file count and
    delegates to the strategy implementation.

    Args:
        folder_path: Path to the folder.
        analyzed_files: List of analyzed files in this folder.
        folder_context: The folder's context information.
        client: The Gemini client.
        model: Model name to use.
        config: Resolved configuration.

    Returns:
        Tuple of (list of proposed renames, token_counts dict).
    """
    # Filter out files that had analysis errors or are unnameable.
    # Files with error/unknown/skipped content_type, or confidence below
    # threshold, should NOT be renamed — they would produce garbage names
    # derived from error messages (see ISSUE-01).
    _SKIP_CONTENT_TYPES = frozenset({"skipped", "error", "unknown"})
    _MIN_CONFIDENCE = 0.1

    processable = []
    for f in analyzed_files:
        if f.summary.content_type in _SKIP_CONTENT_TYPES:
            if logger:
                logger.info(
                    f"  [skipped] {f.enriched.entry.name} — "
                    f"analysis {f.summary.content_type}, excluded from naming"
                )
            continue
        if f.summary.confidence < _MIN_CONFIDENCE:
            if logger:
                logger.info(
                    f"  [skipped] {f.enriched.entry.name} — "
                    f"low confidence ({f.summary.confidence:.2f}), excluded"
                )
            continue
        processable.append(f)

    if not processable:
        return [], {"input_tokens": 0, "output_tokens": 0}

    # All files — including single-file folders — go through the LLM.
    # The deterministic _name_single_file() path produced sentence-fragment
    # names (see ISSUE-10). The marginal cost of one extra API call (~$0.001)
    # is not worth the quality degradation.
    strategy = select_strategy(len(processable))
    return await strategy.generate_names(
        processable, folder_context, client, model, config, logger=logger
    )


async def name_all(
    analyzed_folders: dict[Path, list[AnalyzedFile]],
    folder_contexts: dict[Path, FolderContext],
    client,
    model: str,
    config: Config,
    concurrency: int = 3,
    logger=None,
) -> tuple[dict[Path, list[ProposedRename]], dict]:
    """
    Generate names for all folders concurrently.

    Args:
        analyzed_folders: Dict of folder path -> analyzed files.
        folder_contexts: Dict of folder path -> folder context.
        client: The Gemini client.
        model: Model name to use.
        config: Resolved configuration.
        concurrency: Max concurrent naming operations.

    Returns:
        Tuple of (dict mapping folder paths to lists of proposed renames,
        token_counts dict with total input/output tokens).
    """
    semaphore = asyncio.Semaphore(concurrency)
    results: dict[Path, list[ProposedRename]] = {}
    all_tokens = {"input_tokens": 0, "output_tokens": 0}

    async def process(folder_path: Path):
        nonlocal all_tokens
        async with semaphore:
            context = folder_contexts.get(folder_path)
            files = analyzed_folders.get(folder_path, [])

            if context is None or not files:
                results[folder_path] = []
                return

            try:
                renames, folder_tokens = await name_folder(
                    folder_path, files, context, client, model, config, logger=logger
                )
                results[folder_path] = renames
                all_tokens = _add_token_counts(all_tokens, folder_tokens)
            except Exception:
                results[folder_path] = []

    tasks = [process(path) for path in analyzed_folders]
    await asyncio.gather(*tasks)
    return results, all_tokens
