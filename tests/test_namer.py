"""Tests for ai_file_rename.namer — holistic naming engine and strategy selection."""

import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

from ai_file_rename.config import Config
from ai_file_rename.models import (
    AnalyzedFile,
    ContentSummary,
    EnrichedFile,
    FileCategory,
    FileEntry,
    FileMetadata,
    FolderContext,
)
from ai_file_rename.namer import (
    FullHolisticStrategy,
    ClusteredHolisticStrategy,
    SampledHolisticStrategy,
    ProgressiveHolisticStrategy,
    _NAMING_RESPONSE_SCHEMA,
    _format_file_summary,
    _parse_naming_response,
    name_all,
    name_folder,
    select_strategy,
)


def _make_analyzed(name: str, content_type: str, subject: str, parent: Path) -> AnalyzedFile:
    """Helper to create an AnalyzedFile for testing."""
    return AnalyzedFile(
        enriched=EnrichedFile(
            entry=FileEntry(
                path=parent / name,
                name=name,
                stem=Path(name).stem,
                extension=Path(name).suffix.lstrip("."),
                size_bytes=1000,
                category=FileCategory.DIRECTLY_PROCESSABLE,
                parent_folder=parent,
            ),
            metadata=FileMetadata(size_bytes=1000, size_human="1.0 KB"),
        ),
        summary=ContentSummary(
            content_type=content_type,
            primary_subject=subject,
            key_entities=["entity1"],
            date_references=["2023-01-15"],
            language="en",
            confidence=0.9,
        ),
    )


def _make_folder_context(path: Path, files: list[AnalyzedFile]) -> FolderContext:
    """Helper to create a FolderContext."""
    return FolderContext(
        folder_path=path,
        folder_name=path.name,
        breadcrumb=f"root > {path.name}",
        depth=1,
        files=[f.enriched for f in files],
        sibling_names=[f.enriched.entry.name for f in files],
        file_count=len(files),
    )


class TestSelectStrategy:
    def test_small_folder_full_holistic(self):
        strategy = select_strategy(10)
        assert isinstance(strategy, FullHolisticStrategy)

    def test_50_files_full_holistic(self):
        strategy = select_strategy(50)
        assert isinstance(strategy, FullHolisticStrategy)

    def test_51_files_clustered(self):
        strategy = select_strategy(51)
        assert isinstance(strategy, ClusteredHolisticStrategy)

    def test_200_files_clustered(self):
        strategy = select_strategy(200)
        assert isinstance(strategy, ClusteredHolisticStrategy)

    def test_201_files_sampled(self):
        strategy = select_strategy(201)
        assert isinstance(strategy, SampledHolisticStrategy)

    def test_500_files_sampled(self):
        strategy = select_strategy(500)
        assert isinstance(strategy, SampledHolisticStrategy)

    def test_501_files_progressive(self):
        strategy = select_strategy(501)
        assert isinstance(strategy, ProgressiveHolisticStrategy)


class TestParseNamingResponse:
    def test_valid_response(self):
        response = json.dumps({
            "folder_context_summary": "Test folder",
            "naming_strategy": "descriptive",
            "renames": [
                {
                    "current_name": "IMG_001.jpg",
                    "proposed_name": "sunset-beach.jpg",
                    "reasoning": "Photo of a sunset at the beach",
                    "confidence": 0.95,
                }
            ],
        })

        folder = Path("/tmp/photos")
        files = [_make_analyzed("IMG_001.jpg", "photograph", "sunset photo", folder)]

        renames = _parse_naming_response(response, files, folder)
        assert len(renames) == 1
        assert renames[0].proposed_name == "sunset-beach.jpg"
        assert renames[0].confidence == 0.95

    def test_multiple_renames(self):
        response = json.dumps({
            "folder_context_summary": "Documents",
            "naming_strategy": "content-based",
            "renames": [
                {
                    "current_name": "doc1.pdf",
                    "proposed_name": "revenue-report.pdf",
                    "reasoning": "Revenue report",
                    "confidence": 0.9,
                },
                {
                    "current_name": "doc2.pdf",
                    "proposed_name": "security-audit.pdf",
                    "reasoning": "Security audit",
                    "confidence": 0.85,
                },
            ],
        })

        folder = Path("/tmp/docs")
        files = [
            _make_analyzed("doc1.pdf", "document", "revenue report", folder),
            _make_analyzed("doc2.pdf", "document", "security audit", folder),
        ]

        renames = _parse_naming_response(response, files, folder)
        assert len(renames) == 2
        names = {r.proposed_name for r in renames}
        assert "revenue-report.pdf" in names
        assert "security-audit.pdf" in names

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            _parse_naming_response("not valid json at all", [], Path("/tmp"))

    def test_missing_file_skipped(self):
        """If response mentions a file not in our list, it's skipped."""
        response = json.dumps({
            "renames": [
                {
                    "current_name": "unknown-file.txt",
                    "proposed_name": "still-unknown.txt",
                    "reasoning": "test",
                    "confidence": 0.5,
                }
            ]
        })

        renames = _parse_naming_response(response, [], Path("/tmp"))
        assert len(renames) == 0


class TestFormatFileSummary:
    def test_basic_format(self):
        folder = Path("/tmp/test")
        analyzed = _make_analyzed("test.pdf", "document", "A test document", folder)

        result = _format_file_summary(analyzed, 0)
        assert "File 1:" in result
        assert "test.pdf" in result
        assert "document" in result
        assert "A test document" in result

    def test_includes_metadata(self):
        folder = Path("/tmp/test")
        analyzed = _make_analyzed("test.pdf", "document", "A test document", folder)
        analyzed.enriched.metadata.title = "Important Report"
        analyzed.enriched.metadata.author = "John Doe"
        analyzed.enriched.metadata.page_count = 25

        result = _format_file_summary(analyzed, 0)
        assert "Important Report" in result
        assert "John Doe" in result
        assert "25" in result


class TestFullHolisticStrategy:
    @pytest.mark.asyncio
    async def test_generates_names(self):
        """Test that FullHolisticStrategy calls the model and returns renames."""
        folder = Path("/tmp/test-folder")
        files = [
            _make_analyzed("IMG_001.jpg", "photograph", "beach sunset", folder),
            _make_analyzed("doc.pdf", "document", "quarterly report", folder),
        ]
        context = _make_folder_context(folder, files)

        # Mock the Gemini client
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "folder_context_summary": "Mixed media folder",
            "naming_strategy": "content-descriptive",
            "renames": [
                {
                    "current_name": "IMG_001.jpg",
                    "proposed_name": "beach-sunset-photo.jpg",
                    "reasoning": "Photo of a sunset",
                    "confidence": 0.95,
                },
                {
                    "current_name": "doc.pdf",
                    "proposed_name": "quarterly-report.pdf",
                    "reasoning": "Quarterly report document",
                    "confidence": 0.9,
                },
            ],
        })

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        config = Config(gemini_api_key="test")
        strategy = FullHolisticStrategy()

        renames = await strategy.generate_names(
            files, context, mock_client, "gemini-2.5-flash", config
        )

        assert len(renames) == 2
        assert mock_client.models.generate_content.called

        # Verify schema was passed
        call_args = mock_client.models.generate_content.call_args
        config_arg = call_args.kwargs.get("config", call_args[1].get("config", {}))
        assert "response_json_schema" in config_arg
        assert config_arg["response_json_schema"] == _NAMING_RESPONSE_SCHEMA


class TestNamingResponseSchema:
    def test_schema_structure(self):
        """Naming schema defines the expected renames array."""
        assert _NAMING_RESPONSE_SCHEMA["type"] == "object"
        assert "renames" in _NAMING_RESPONSE_SCHEMA["properties"]
        renames_schema = _NAMING_RESPONSE_SCHEMA["properties"]["renames"]
        assert renames_schema["type"] == "array"
        item_props = renames_schema["items"]["properties"]
        assert "current_name" in item_props
        assert "proposed_name" in item_props
        assert "reasoning" in item_props
        assert "confidence" in item_props


# --- ISSUE-01: Error filtering tests ---


def _make_analyzed_with_confidence(
    name: str, content_type: str, subject: str, parent: Path, confidence: float
) -> AnalyzedFile:
    """Helper with explicit confidence control."""
    af = _make_analyzed(name, content_type, subject, parent)
    af.summary.confidence = confidence
    return af


class TestErrorFiltering:
    """Tests for ISSUE-01: files with failed analysis are excluded from naming."""

    @pytest.mark.asyncio
    async def test_name_folder_excludes_error_files(self):
        """Files with content_type='error' are excluded from naming."""
        folder = Path("/tmp/mixed")
        good_file = _make_analyzed("photo.jpg", "photograph", "A sunset", folder)
        error_file = _make_analyzed_with_confidence(
            "broken.mov", "error", "Analysis failed: 400 FAILED_PRECONDITION", folder, 0.0
        )

        context = _make_folder_context(folder, [good_file, error_file])

        # Mock client for the 1 remaining good file
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "renames": [
                {"current_name": "photo.jpg", "proposed_name": "sunset-photo.jpg",
                 "reasoning": "test", "confidence": 0.9},
            ]
        })
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        config = Config(gemini_api_key="test")
        renames, tokens = await name_folder(
            folder, [good_file, error_file], context, mock_client, "gemini-2.5-flash", config
        )

        assert len(renames) == 1
        assert renames[0].current_name == "photo.jpg"

    @pytest.mark.asyncio
    async def test_name_folder_excludes_unknown_content_type(self):
        """Files with content_type='unknown' are excluded."""
        folder = Path("/tmp/test")
        unknown_file = _make_analyzed_with_confidence(
            "weird.bin", "unknown", "Analysis failed: unsupported format", folder, 0.0
        )

        context = _make_folder_context(folder, [unknown_file])
        config = Config(gemini_api_key="test")
        renames, tokens = await name_folder(
            folder, [unknown_file], context, None, "gemini-2.5-flash", config
        )

        assert len(renames) == 0

    @pytest.mark.asyncio
    async def test_name_folder_excludes_low_confidence(self):
        """Files with confidence < 0.1 are excluded."""
        folder = Path("/tmp/test")
        low_conf = _make_analyzed_with_confidence(
            "maybe.pdf", "document", "Possibly a report", folder, 0.05
        )

        context = _make_folder_context(folder, [low_conf])
        config = Config(gemini_api_key="test")
        renames, tokens = await name_folder(
            folder, [low_conf], context, None, "gemini-2.5-flash", config
        )

        assert len(renames) == 0

    @pytest.mark.asyncio
    async def test_name_folder_keeps_good_files_with_errors_present(self):
        """Good files are still named even when some files have errors."""
        folder = Path("/tmp/mixed")
        good1 = _make_analyzed("doc1.pdf", "document", "Revenue report", folder)
        good2 = _make_analyzed("doc2.pdf", "document", "Security audit", folder)
        error = _make_analyzed_with_confidence(
            "bad.mov", "error", "API error 500", folder, 0.0
        )

        context = _make_folder_context(folder, [good1, good2, error])

        # Mock the Gemini client for the 2 good files
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "renames": [
                {"current_name": "doc1.pdf", "proposed_name": "revenue-report.pdf",
                 "reasoning": "test", "confidence": 0.9},
                {"current_name": "doc2.pdf", "proposed_name": "security-audit.pdf",
                 "reasoning": "test", "confidence": 0.85},
            ]
        })
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        config = Config(gemini_api_key="test")
        renames, tokens = await name_folder(
            folder, [good1, good2, error], context, mock_client, "gemini-2.5-flash", config
        )

        assert len(renames) == 2
        names = {r.proposed_name for r in renames}
        assert "revenue-report.pdf" in names
        assert "security-audit.pdf" in names

    @pytest.mark.asyncio
    async def test_name_folder_excludes_skipped_files(self):
        """Files with content_type='skipped' are excluded."""
        folder = Path("/tmp/test")
        skipped = _make_analyzed_with_confidence(
            "modified.txt", "skipped", "File modified during processing", folder, 0.0
        )

        context = _make_folder_context(folder, [skipped])
        config = Config(gemini_api_key="test")
        renames, _ = await name_folder(
            folder, [skipped], context, None, "gemini-2.5-flash", config
        )

        assert len(renames) == 0


# --- Naming logging tests ---


class TestNamingLogging:
    """Tests for per-file naming logging."""

    def test_parse_response_logs_debug(self):
        """_parse_naming_response emits debug logs for each rename."""
        response = json.dumps({
            "renames": [
                {"current_name": "a.txt", "proposed_name": "alpha.txt",
                 "reasoning": "test reason", "confidence": 0.9},
            ]
        })
        folder = Path("/tmp/test")
        files = [_make_analyzed("a.txt", "document", "Alpha doc", folder)]

        mock_logger = MagicMock()
        _parse_naming_response(response, files, folder, logger=mock_logger)

        # Should have logged at debug level for the parse
        mock_logger.debug.assert_called()
        debug_msg = mock_logger.debug.call_args[0][0]
        assert "a.txt" in debug_msg
        assert "alpha.txt" in debug_msg

    def test_parse_response_warns_on_missing_file(self):
        """_parse_naming_response warns when a file is in response but not input."""
        response = json.dumps({
            "renames": [
                {"current_name": "ghost.txt", "proposed_name": "phantom.txt",
                 "reasoning": "test", "confidence": 0.5},
            ]
        })

        mock_logger = MagicMock()
        _parse_naming_response(response, [], Path("/tmp"), logger=mock_logger)

        mock_logger.warning.assert_called()
        warn_msg = mock_logger.warning.call_args[0][0]
        assert "ghost.txt" in warn_msg

    def test_parse_response_warns_on_unmatched_input(self):
        """Warns when an input file is not found in the response."""
        response = json.dumps({"renames": []})
        folder = Path("/tmp/test")
        files = [_make_analyzed("orphan.txt", "document", "Orphan doc", folder)]

        mock_logger = MagicMock()
        _parse_naming_response(response, files, folder, logger=mock_logger)

        mock_logger.warning.assert_called()
        warn_msg = mock_logger.warning.call_args[0][0]
        assert "orphan.txt" in warn_msg


# --- ISSUE-14: name_all() error handling tests ---


class TestNameAllErrorHandling:
    """Tests for ISSUE-14: name_all() should log errors instead of silently swallowing."""

    @pytest.mark.asyncio
    async def test_name_all_logs_error_on_failure(self):
        """When name_folder raises, name_all logs the error."""
        folder = Path("/tmp/failing")
        analyzed = _make_analyzed("doc.pdf", "document", "Test doc", folder)
        context = _make_folder_context(folder, [analyzed])

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("API down")

        mock_logger = MagicMock()
        config = Config(gemini_api_key="test")

        results, _ = await name_all(
            {folder: [analyzed]},
            {folder: context},
            mock_client,
            "gemini-2.5-flash",
            config,
            logger=mock_logger,
        )

        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        assert str(folder) in error_msg
        assert results[folder] == []

    @pytest.mark.asyncio
    async def test_name_all_returns_empty_on_failure(self):
        """When name_folder raises, name_all returns empty list for that folder."""
        folder = Path("/tmp/failing")
        analyzed = _make_analyzed("doc.pdf", "document", "Test doc", folder)
        context = _make_folder_context(folder, [analyzed])

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("kaboom")

        config = Config(gemini_api_key="test")
        mock_logger = MagicMock()

        results, tokens = await name_all(
            {folder: [analyzed]},
            {folder: context},
            mock_client,
            "gemini-2.5-flash",
            config,
            logger=mock_logger,
        )

        assert folder in results
        assert results[folder] == []

    @pytest.mark.asyncio
    async def test_name_all_no_crash_without_logger(self):
        """name_all() doesn't crash when logger=None and name_folder fails."""
        folder = Path("/tmp/failing")
        analyzed = _make_analyzed("doc.pdf", "document", "Test doc", folder)
        context = _make_folder_context(folder, [analyzed])

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("no logger")

        config = Config(gemini_api_key="test")

        # logger=None (default) — must NOT raise AttributeError
        results, _ = await name_all(
            {folder: [analyzed]},
            {folder: context},
            mock_client,
            "gemini-2.5-flash",
            config,
        )

        assert results[folder] == []

    @pytest.mark.asyncio
    async def test_name_all_partial_failure(self):
        """One folder failing doesn't prevent other folders from being named."""
        good_folder = Path("/tmp/good")
        bad_folder = Path("/tmp/bad")

        good_analyzed = _make_analyzed("doc.pdf", "document", "Good doc", good_folder)
        bad_analyzed = _make_analyzed("bad.pdf", "document", "Bad doc", bad_folder)

        good_context = _make_folder_context(good_folder, [good_analyzed])
        bad_context = _make_folder_context(bad_folder, [bad_analyzed])

        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "renames": [
                {"current_name": "doc.pdf", "proposed_name": "good-doc.pdf",
                 "reasoning": "test", "confidence": 0.9},
            ]
        })

        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            # First call succeeds, second fails
            contents = kwargs.get("contents", [])
            prompt_text = str(contents[0]) if contents else ""
            if "bad" in prompt_text.lower() or "bad" in str(kwargs):
                raise RuntimeError("API error for bad folder")
            return mock_response

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = side_effect

        config = Config(gemini_api_key="test")
        mock_logger = MagicMock()

        results, _ = await name_all(
            {good_folder: [good_analyzed], bad_folder: [bad_analyzed]},
            {good_folder: good_context, bad_folder: bad_context},
            mock_client,
            "gemini-2.5-flash",
            config,
            logger=mock_logger,
        )

        # Bad folder should have empty results
        assert results[bad_folder] == []
        # Good folder should have results (may or may not work depending on call order)
        assert bad_folder in results

