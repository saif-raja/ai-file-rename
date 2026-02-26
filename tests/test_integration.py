"""Integration tests for ai-file-rename — end-to-end pipeline with mocked Gemini."""

import json
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_file_rename.config import Config
from ai_file_rename.context import build_context
from ai_file_rename.discovery import discover
from ai_file_rename.executor import execute_renames, undo_renames
from ai_file_rename.manifest import Manifest
from ai_file_rename.models import (
    ContentSummary,
    EnrichedFile,
    FileCategory,
    FileMetadata,
    ProposedRename,
    ValidatedRename,
)
from ai_file_rename.preprocessing import preprocess
from ai_file_rename.validator import validate_renames


FIXTURES = Path(__file__).parent / "fixtures" / "sample-files"
MOCK_RESPONSES = Path(__file__).parent / "fixtures" / "mock-responses"


class TestDiscoveryToPreprocessing:
    """Test the discovery -> preprocessing pipeline."""

    def test_full_discovery_pipeline(self):
        config = Config(gemini_api_key="test", max_files=500)
        result = discover(FIXTURES, recursive=True, config=config)

        # Should find many files across categories
        categories = {f.category for f in result.files}
        assert FileCategory.DIRECTLY_PROCESSABLE in categories
        assert FileCategory.TEXT_EXTRACTABLE in categories
        assert FileCategory.UNSUPPORTED in categories

        # File type breakdown should be populated
        assert len(result.impact.file_type_breakdown) > 5

    def test_discovery_to_preprocessing(self, temp_dir):
        config = Config(gemini_api_key="test")
        result = discover(FIXTURES / "text", recursive=False, config=config)

        processable = [f for f in result.files if f.category != FileCategory.UNSUPPORTED]
        enriched = preprocess(processable, temp_dir, config)

        assert len(enriched) == len(processable)
        for e in enriched:
            assert e.metadata is not None
            assert e.metadata.size_bytes >= 0

    def test_discovery_to_context(self, temp_dir):
        config = Config(gemini_api_key="test")
        result = discover(FIXTURES / "mixed-folder", recursive=False, config=config)

        processable = [f for f in result.files if f.category != FileCategory.UNSUPPORTED]
        enriched = preprocess(processable, temp_dir, config)

        contexts = build_context(enriched, FIXTURES / "mixed-folder")
        assert len(contexts) >= 1

        for ctx in contexts.values():
            assert ctx.file_count > 0
            assert len(ctx.breadcrumb) > 0


class TestValidationToExecution:
    """Test the validation -> execution pipeline."""

    def test_validate_and_execute(self, temp_dir):
        """Full pipeline from validation through execution."""
        # Create test files
        (temp_dir / "IMG_001.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
        (temp_dir / "document.pdf").write_bytes(b"%PDF-1.4 test content")
        (temp_dir / "notes.txt").write_text("Meeting notes from Q3")

        # Create proposed renames (as if Gemini generated them)
        proposed = [
            ProposedRename(
                current_name="IMG_001.jpg",
                proposed_name="team-meeting-photo.jpg",
                current_path=temp_dir / "IMG_001.jpg",
                proposed_path=temp_dir / "team-meeting-photo.jpg",
                reasoning="Photo of team meeting",
                confidence=0.9,
            ),
            ProposedRename(
                current_name="document.pdf",
                proposed_name="quarterly-report-q3.pdf",
                current_path=temp_dir / "document.pdf",
                proposed_path=temp_dir / "quarterly-report-q3.pdf",
                reasoning="Q3 quarterly report",
                confidence=0.95,
            ),
            ProposedRename(
                current_name="notes.txt",
                proposed_name="q3-meeting-notes.txt",
                current_path=temp_dir / "notes.txt",
                proposed_path=temp_dir / "q3-meeting-notes.txt",
                reasoning="Meeting notes from Q3 planning",
                confidence=0.88,
            ),
        ]

        # Validate
        validated = validate_renames(proposed)
        assert len(validated) == 3

        # No collisions
        names = {v.final_name for v in validated}
        assert len(names) == 3

        # Execute
        config = Config(gemini_api_key="test")
        result = execute_renames(validated, temp_dir, "int-test-001", config)

        assert result.renamed == 3
        assert result.failed == 0

        # Verify files exist with new names
        assert (temp_dir / "team-meeting-photo.jpg").exists()
        assert (temp_dir / "quarterly-report-q3.pdf").exists()
        assert (temp_dir / "q3-meeting-notes.txt").exists()

        # Old names should be gone
        assert not (temp_dir / "IMG_001.jpg").exists()
        assert not (temp_dir / "document.pdf").exists()
        assert not (temp_dir / "notes.txt").exists()

    def test_validate_execute_undo(self, temp_dir):
        """Full pipeline including undo."""
        (temp_dir / "original.txt").write_text("important content")

        proposed = [
            ProposedRename(
                current_name="original.txt",
                proposed_name="descriptive-name.txt",
                current_path=temp_dir / "original.txt",
                proposed_path=temp_dir / "descriptive-name.txt",
                reasoning="More descriptive",
                confidence=0.9,
            ),
        ]

        validated = validate_renames(proposed)
        config = Config(gemini_api_key="test")
        result = execute_renames(validated, temp_dir, "undo-test", config)

        assert result.renamed == 1
        assert (temp_dir / "descriptive-name.txt").exists()

        # Recreate manifest for undo
        manifest = Manifest(temp_dir, "undo-test")
        manifest.create(validated)
        manifest.record_success(0)

        # Undo
        undo_result = undo_renames(temp_dir)
        assert undo_result.renamed == 1
        assert (temp_dir / "original.txt").exists()
        assert (temp_dir / "original.txt").read_text() == "important content"


class TestCollisionHandling:
    """Test name collision detection and resolution."""

    def test_internal_collision_resolution(self, temp_dir):
        """Two files get the same proposed name — numeric suffix applied."""
        (temp_dir / "a.pdf").write_bytes(b"pdf a")
        (temp_dir / "b.pdf").write_bytes(b"pdf b")

        proposed = [
            ProposedRename(
                current_name="a.pdf",
                proposed_name="report.pdf",
                current_path=temp_dir / "a.pdf",
                proposed_path=temp_dir / "report.pdf",
                reasoning="test",
                confidence=0.9,
            ),
            ProposedRename(
                current_name="b.pdf",
                proposed_name="report.pdf",
                current_path=temp_dir / "b.pdf",
                proposed_path=temp_dir / "report.pdf",
                reasoning="test",
                confidence=0.9,
            ),
        ]

        validated = validate_renames(proposed)
        names = {v.final_name for v in validated}
        assert len(names) == 2
        assert "report.pdf" in names
        assert "report-2.pdf" in names

    def test_external_collision_resolution(self, temp_dir):
        """Proposed name collides with existing file not being renamed."""
        (temp_dir / "source.pdf").write_bytes(b"source")
        (temp_dir / "existing.pdf").write_bytes(b"existing")

        proposed = [
            ProposedRename(
                current_name="source.pdf",
                proposed_name="existing.pdf",
                current_path=temp_dir / "source.pdf",
                proposed_path=temp_dir / "existing.pdf",
                reasoning="test",
                confidence=0.9,
            ),
        ]

        validated = validate_renames(
            proposed,
            existing_files={"source.pdf", "existing.pdf"},
            files_being_renamed={"source.pdf"},
        )
        assert validated[0].final_name == "existing-2.pdf"


class TestSymlinkIntegration:
    """Test symlink handling through the pipeline."""

    def test_discover_and_execute_with_symlinks(self, temp_dir):
        """Full pipeline with symlinks."""
        # Create real file
        real_file = temp_dir / "real-document.txt"
        real_file.write_text("Important document content")

        # Create symlink
        link = temp_dir / "shortcut.txt"
        os.symlink("real-document.txt", str(link))

        # Discover
        config = Config(gemini_api_key="test")
        result = discover(temp_dir, recursive=False, config=config)

        assert result.impact.symlinks_found >= 1

        # Create a rename for the real file
        proposed = [
            ProposedRename(
                current_name="real-document.txt",
                proposed_name="important-document.txt",
                current_path=real_file,
                proposed_path=temp_dir / "important-document.txt",
                reasoning="Descriptive name",
                confidence=0.9,
                has_incoming_symlinks=True,
            ),
        ]

        validated = validate_renames(proposed, symlink_map=result.symlink_map)
        exec_result = execute_renames(
            validated, temp_dir, "sym-test", config,
            symlink_map=result.symlink_map,
        )

        assert exec_result.renamed == 1
        assert (temp_dir / "important-document.txt").exists()


class TestEdgeCases:
    """Test edge cases in the pipeline."""

    def test_empty_folder(self, temp_dir):
        """Test discovery on an empty folder."""
        config = Config(gemini_api_key="test")
        result = discover(temp_dir, recursive=False, config=config)
        assert result.impact.total_files == 0

    def test_single_file(self, temp_dir):
        """Test with a single file."""
        (temp_dir / "lonely.txt").write_text("I am alone")
        config = Config(gemini_api_key="test")
        result = discover(temp_dir, recursive=False, config=config)
        assert result.impact.total_files == 1

    def test_unicode_filename_handling(self, temp_dir):
        """Test that Unicode filenames are handled correctly."""
        (temp_dir / "café-résumé.txt").write_text("unicode test")

        proposed = [
            ProposedRename(
                current_name="café-résumé.txt",
                proposed_name="cafe-resume.txt",
                current_path=temp_dir / "café-résumé.txt",
                proposed_path=temp_dir / "cafe-resume.txt",
                reasoning="ASCII transliteration",
                confidence=0.9,
            ),
        ]

        validated = validate_renames(proposed)
        assert validated[0].final_name == "cafe-resume.txt"

        config = Config(gemini_api_key="test")
        result = execute_renames(validated, temp_dir, "unicode-test", config)
        assert result.renamed == 1
        assert (temp_dir / "cafe-resume.txt").exists()

    def test_very_long_name_truncated(self, temp_dir):
        """Test that very long names get truncated."""
        long_stem = "word-" * 50  # 250 chars
        long_name = f"{long_stem}.txt"

        proposed = [
            ProposedRename(
                current_name="source.txt",
                proposed_name=long_name,
                current_path=temp_dir / "source.txt",
                proposed_path=temp_dir / long_name,
                reasoning="test",
                confidence=0.9,
            ),
        ]

        validated = validate_renames(proposed)
        # Final name should be <= 200 chars
        assert len(validated[0].final_name) <= 200

    def test_windows_reserved_name_handled(self, temp_dir):
        """Test that Windows reserved names are handled."""
        proposed = [
            ProposedRename(
                current_name="source.txt",
                proposed_name="CON.txt",
                current_path=temp_dir / "source.txt",
                proposed_path=temp_dir / "CON.txt",
                reasoning="test",
                confidence=0.9,
            ),
        ]

        validated = validate_renames(proposed)
        # Should be prefixed to avoid reserved name
        assert not validated[0].final_name.lower().startswith("con.")
