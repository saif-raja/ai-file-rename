"""Tests for ai_file_rename.analyzer: content analysis with Gemini."""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_file_rename.analyzer import (
    _CONTENT_SUMMARY_SCHEMA,
    _analyze_single_file,
    _build_analysis_prompt,
    _format_metadata_for_prompt,
    _get_mtime,
    _parse_content_summary,
    create_batches,
)
from ai_file_rename.models import (
    ContentSummary,
    EnrichedFile,
    FileCategory,
    FileEntry,
    FileMetadata,
    FolderContext,
)


def _make_enriched(
    name: str, size: int, ext: str = "pdf",
    category: FileCategory = FileCategory.DIRECTLY_PROCESSABLE,
) -> EnrichedFile:
    parent = Path("/tmp/test")
    return EnrichedFile(
        entry=FileEntry(
            path=parent / name,
            name=name,
            stem=Path(name).stem,
            extension=ext,
            size_bytes=size,
            category=category,
            parent_folder=parent,
        ),
        metadata=FileMetadata(
            size_bytes=size,
            size_human=f"{size} B",
            title="Test Title" if ext == "pdf" else None,
            author="Test Author" if ext == "pdf" else None,
        ),
    )


class TestFormatMetadataForPrompt:
    def test_with_metadata(self):
        enriched = _make_enriched("test.pdf", 1000)
        enriched.metadata.title = "My Document"
        enriched.metadata.author = "Jane Doe"
        enriched.metadata.page_count = 15

        result = _format_metadata_for_prompt(enriched)
        assert "My Document" in result
        assert "Jane Doe" in result
        assert "15" in result

    def test_empty_metadata_returns_null(self):
        enriched = _make_enriched("test.txt", 100, "txt", FileCategory.TEXT_EXTRACTABLE)
        enriched.metadata.title = None
        enriched.metadata.author = None

        result = _format_metadata_for_prompt(enriched)
        assert result == "null"

    def test_with_dimensions(self):
        enriched = _make_enriched("photo.jpg", 5000, "jpg")
        enriched.metadata.dimensions = "3840x2160"

        result = _format_metadata_for_prompt(enriched)
        assert "3840x2160" in result

    def test_with_duration(self):
        enriched = _make_enriched("audio.mp3", 10000, "mp3")
        enriched.metadata.duration_seconds = 185.5

        result = _format_metadata_for_prompt(enriched)
        assert "3m05s" in result


class TestParseContentSummary:
    def test_valid_json(self):
        response = json.dumps({
            "content_type": "document",
            "primary_subject": "A quarterly report",
            "key_entities": ["revenue", "Q3", "2023"],
            "date_references": ["2023-09-30"],
            "language": "en",
            "confidence": 0.92,
        })

        summary = _parse_content_summary(response)
        assert isinstance(summary, ContentSummary)
        assert summary.content_type == "document"
        assert summary.confidence == 0.92
        assert "revenue" in summary.key_entities

    def test_invalid_json_fallback(self):
        summary = _parse_content_summary("completely invalid")
        assert summary.content_type == "unknown"
        assert summary.confidence == 0.0

    def test_partial_json(self):
        response = json.dumps({
            "content_type": "photograph",
            "primary_subject": "A sunset",
        })

        summary = _parse_content_summary(response)
        assert summary.content_type == "photograph"
        # Missing fields should have defaults
        assert summary.key_entities == []
        assert summary.language == "unknown"


class TestCreateBatches:
    def test_single_batch_small_files(self):
        files = [_make_enriched(f"file{i}.pdf", 1000) for i in range(5)]
        batches = create_batches(files, max_batch_bytes=80_000_000)
        assert len(batches) == 1
        assert len(batches[0]) == 5

    def test_multiple_batches_large_files(self):
        files = [
            _make_enriched(f"file{i}.pdf", 30_000_000)
            for i in range(5)
        ]
        batches = create_batches(files, max_batch_bytes=80_000_000)
        assert len(batches) >= 2

    def test_text_files_separate_batch(self):
        files = [
            _make_enriched("doc.pdf", 1000),
            _make_enriched("notes.txt", 500, "txt", FileCategory.TEXT_EXTRACTABLE),
        ]
        batches = create_batches(files, max_batch_bytes=80_000_000)
        # Should have at least 2 batches: one for uploadable, one for text
        assert len(batches) >= 2

    def test_empty_list(self):
        batches = create_batches([])
        assert len(batches) == 0

    def test_sorted_by_size(self):
        files = [
            _make_enriched("big.pdf", 5_000_000),
            _make_enriched("small.pdf", 100),
            _make_enriched("medium.pdf", 500_000),
        ]
        batches = create_batches(files, max_batch_bytes=80_000_000)
        # Within a batch, files should be sorted by size ascending
        for batch in batches:
            sizes = [f.metadata.size_bytes for f in batch]
            assert sizes == sorted(sizes)


class TestBuildAnalysisPrompt:
    def test_prompt_contains_file_info(self):
        enriched = _make_enriched("test.pdf", 1000)
        context = FolderContext(
            folder_path=Path("/tmp/test"),
            folder_name="test",
            breadcrumb="root > test",
            depth=1,
            files=[enriched],
            sibling_names=["test.pdf"],
            file_count=1,
        )

        prompt = _build_analysis_prompt(enriched, context)
        assert "test.pdf" in prompt
        assert "test" in prompt  # folder name
        assert "root > test" in prompt  # breadcrumb


class TestContentSummarySchema:
    def test_schema_is_valid_json_schema(self):
        """ContentSummary schema has required JSON Schema structure."""
        assert _CONTENT_SUMMARY_SCHEMA["type"] == "object"
        assert "properties" in _CONTENT_SUMMARY_SCHEMA
        props = _CONTENT_SUMMARY_SCHEMA["properties"]
        assert "content_type" in props
        assert "primary_subject" in props
        assert "key_entities" in props
        assert "confidence" in props

    def test_schema_has_required_fields(self):
        """Schema includes required fields list."""
        required = _CONTENT_SUMMARY_SCHEMA.get("required", [])
        assert "content_type" in required
        assert "primary_subject" in required

    def test_schema_is_passed_to_api_call(self, tmp_path):
        """Verify the schema is passed in the generate_content config."""
        f = tmp_path / "test.txt"
        f.write_text("content")

        enriched = EnrichedFile(
            entry=FileEntry(
                path=f, name="test.txt", stem="test", extension="txt",
                size_bytes=100, category=FileCategory.TEXT_EXTRACTABLE,
                parent_folder=tmp_path,
            ),
            metadata=FileMetadata(size_bytes=100, size_human="100 B"),
        )
        context = FolderContext(
            folder_path=tmp_path, folder_name="test", breadcrumb="root > test",
            depth=1, files=[enriched], sibling_names=["test.txt"], file_count=1,
        )

        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "content_type": "text", "primary_subject": "test",
            "key_entities": [], "date_references": [],
            "language": "en", "confidence": 0.9,
        })
        mock_response.usage_metadata = None
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        asyncio.run(
            _analyze_single_file(enriched, context, mock_client, "gemini-2.5-flash")
        )

        # Verify the config dict passed to the API includes the schema
        call_args = mock_client.models.generate_content.call_args
        config_arg = call_args.kwargs.get("config", call_args[1].get("config", {}))
        assert "response_json_schema" in config_arg
        assert config_arg["response_json_schema"] == _CONTENT_SUMMARY_SCHEMA


class TestGetMtime:
    def test_returns_mtime_for_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert _get_mtime(f) > 0

    def test_returns_zero_for_missing_file(self):
        assert _get_mtime(Path("/nonexistent/file.txt")) == 0.0


class TestFileModifiedDuringProcessing:
    def test_skipped_when_mtime_changes(self, tmp_path):
        """File modified during analysis is skipped."""
        f = tmp_path / "changing.txt"
        f.write_text("original content")

        enriched = EnrichedFile(
            entry=FileEntry(
                path=f,
                name="changing.txt",
                stem="changing",
                extension="txt",
                size_bytes=100,
                category=FileCategory.TEXT_EXTRACTABLE,
                parent_folder=tmp_path,
            ),
            metadata=FileMetadata(size_bytes=100, size_human="100 B"),
        )
        context = FolderContext(
            folder_path=tmp_path,
            folder_name="test",
            breadcrumb="root > test",
            depth=1,
            files=[enriched],
            sibling_names=["changing.txt"],
            file_count=1,
        )

        # Mock the client to simulate an API call, and change mtime mid-flight
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "content_type": "text",
            "primary_subject": "test",
            "key_entities": [],
            "date_references": [],
            "language": "en",
            "confidence": 0.9,
        })
        mock_response.usage_metadata = None

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        # Simulate mtime change: return different values on successive calls
        call_count = [0]
        def mock_mtime(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return 1000.0  # before
            return 2000.0  # after (different = modified)

        with patch("ai_file_rename.analyzer._get_mtime", side_effect=mock_mtime):
            result, tokens = asyncio.run(
                _analyze_single_file(enriched, context, mock_client, "gemini-2.5-flash")
            )

        assert result.summary.content_type == "skipped"
        assert "modified during processing" in result.summary.primary_subject


class TestJsonRetry:
    def test_retry_on_invalid_json(self, tmp_path):
        """Gemini retries once when response is not valid JSON."""
        f = tmp_path / "test.txt"
        f.write_text("content")

        enriched = EnrichedFile(
            entry=FileEntry(
                path=f,
                name="test.txt",
                stem="test",
                extension="txt",
                size_bytes=100,
                category=FileCategory.TEXT_EXTRACTABLE,
                parent_folder=tmp_path,
            ),
            metadata=FileMetadata(size_bytes=100, size_human="100 B"),
        )
        context = FolderContext(
            folder_path=tmp_path,
            folder_name="test",
            breadcrumb="root > test",
            depth=1,
            files=[enriched],
            sibling_names=["test.txt"],
            file_count=1,
        )

        good_json = json.dumps({
            "content_type": "text",
            "primary_subject": "test content",
            "key_entities": [],
            "date_references": [],
            "language": "en",
            "confidence": 0.85,
        })

        # First response is garbage, retry response is valid
        bad_response = MagicMock()
        bad_response.text = "not valid json at all!!!"
        bad_response.usage_metadata = None

        good_response = MagicMock()
        good_response.text = good_json
        good_response.usage_metadata = None

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [bad_response, good_response]

        result, tokens = asyncio.run(
            _analyze_single_file(enriched, context, mock_client, "gemini-2.5-flash")
        )

        # Should have called generate_content twice (original + retry)
        assert mock_client.models.generate_content.call_count == 2
        assert result.summary.content_type == "text"
        assert result.summary.confidence == 0.85


# --- ISSUE-13: Gemini file upload cleanup tests ---


def _make_uploadable_enriched(tmp_path):
    """Create an enriched file that triggers the Gemini upload path."""
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
    processed = tmp_path / "photo_converted.png"
    processed.write_bytes(b"\x89PNG" + b"\x00" * 100)

    enriched = EnrichedFile(
        entry=FileEntry(
            path=f,
            name="photo.jpg",
            stem="photo",
            extension="jpg",
            size_bytes=104,
            category=FileCategory.DIRECTLY_PROCESSABLE,
            parent_folder=tmp_path,
        ),
        metadata=FileMetadata(size_bytes=104, size_human="104 B"),
        processed_path=processed,
    )
    return enriched


def _make_folder_context_for(tmp_path, enriched):
    """Create a FolderContext for a single enriched file."""
    return FolderContext(
        folder_path=tmp_path,
        folder_name="test",
        breadcrumb="root > test",
        depth=1,
        files=[enriched],
        sibling_names=[enriched.entry.name],
        file_count=1,
    )


class TestGeminiFileCleanup:
    """Tests for ISSUE-13: uploaded Gemini files must be cleaned up after use."""

    def test_uploaded_file_deleted_after_success(self, tmp_path):
        """Uploaded file is deleted from Gemini after successful analysis."""
        enriched = _make_uploadable_enriched(tmp_path)
        context = _make_folder_context_for(tmp_path, enriched)

        mock_uploaded = MagicMock()
        mock_uploaded.name = "files/abc123"
        mock_uploaded.state = "ACTIVE"

        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "content_type": "photograph",
            "primary_subject": "A sunset",
            "key_entities": [],
            "date_references": [],
            "language": "en",
            "confidence": 0.9,
        })
        mock_response.usage_metadata = None

        mock_client = MagicMock()
        mock_client.files.upload.return_value = mock_uploaded
        mock_client.models.generate_content.return_value = mock_response

        asyncio.run(
            _analyze_single_file(enriched, context, mock_client, "gemini-2.5-flash")
        )

        # Verify the file was cleaned up
        mock_client.files.delete.assert_called_once_with(name="files/abc123")

    def test_uploaded_file_deleted_after_failure(self, tmp_path):
        """Uploaded file is deleted even when generate_content raises."""
        enriched = _make_uploadable_enriched(tmp_path)
        context = _make_folder_context_for(tmp_path, enriched)

        mock_uploaded = MagicMock()
        mock_uploaded.name = "files/def456"
        mock_uploaded.state = "ACTIVE"

        mock_client = MagicMock()
        mock_client.files.upload.return_value = mock_uploaded
        mock_client.models.generate_content.side_effect = RuntimeError("API error")

        asyncio.run(
            _analyze_single_file(enriched, context, mock_client, "gemini-2.5-flash")
        )

        # Cleanup should still happen despite the API error
        mock_client.files.delete.assert_called_once_with(name="files/def456")

    def test_no_cleanup_for_text_files(self, tmp_path):
        """Text-extractable files don't trigger upload or cleanup."""
        f = tmp_path / "notes.txt"
        f.write_text("Meeting notes from Q3 planning session.")

        enriched = EnrichedFile(
            entry=FileEntry(
                path=f, name="notes.txt", stem="notes", extension="txt",
                size_bytes=100, category=FileCategory.TEXT_EXTRACTABLE,
                parent_folder=tmp_path,
            ),
            metadata=FileMetadata(size_bytes=100, size_human="100 B"),
        )
        context = _make_folder_context_for(tmp_path, enriched)

        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "content_type": "document",
            "primary_subject": "Meeting notes",
            "key_entities": [],
            "date_references": [],
            "language": "en",
            "confidence": 0.8,
        })
        mock_response.usage_metadata = None

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        asyncio.run(
            _analyze_single_file(enriched, context, mock_client, "gemini-2.5-flash")
        )

        # No upload or cleanup should have happened
        mock_client.files.upload.assert_not_called()
        mock_client.files.delete.assert_not_called()

    def test_cleanup_failure_logged_at_debug(self, tmp_path):
        """Failed cleanup is logged at debug level, not silently swallowed."""
        enriched = _make_uploadable_enriched(tmp_path)
        context = _make_folder_context_for(tmp_path, enriched)

        mock_uploaded = MagicMock()
        mock_uploaded.name = "files/ghi789"
        mock_uploaded.state = "ACTIVE"

        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "content_type": "photograph",
            "primary_subject": "A sunset",
            "key_entities": [],
            "date_references": [],
            "language": "en",
            "confidence": 0.9,
        })
        mock_response.usage_metadata = None

        mock_client = MagicMock()
        mock_client.files.upload.return_value = mock_uploaded
        mock_client.models.generate_content.return_value = mock_response
        mock_client.files.delete.side_effect = RuntimeError("Cleanup failed")

        mock_logger = MagicMock()

        # Should not raise even though cleanup fails
        result, tokens = asyncio.run(
            _analyze_single_file(
                enriched, context, mock_client, "gemini-2.5-flash", logger=mock_logger
            )
        )

        # Analysis should still succeed
        assert result.summary.content_type == "photograph"
        # Cleanup failure should be logged at debug level
        mock_logger.debug.assert_called()
        debug_msg = mock_logger.debug.call_args[0][0]
        assert "files/ghi789" in debug_msg
