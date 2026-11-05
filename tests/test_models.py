"""Tests for ai_file_rename.models: Pydantic data model validation."""

from datetime import datetime
from pathlib import Path

import pytest

from ai_file_rename.models import (
    AnalyzedFile,
    ContentSummary,
    DiscoveryResult,
    EnrichedFile,
    ExecutionResult,
    FileCategory,
    FileEntry,
    FileMetadata,
    FolderContext,
    FolderEntry,
    ImpactSummary,
    ProposedRename,
    RenameResult,
    SymlinkEntry,
    ValidatedRename,
)


class TestFileCategory:
    def test_enum_values(self):
        assert FileCategory.DIRECTLY_PROCESSABLE == "directly_processable"
        assert FileCategory.CONVERTIBLE == "convertible"
        assert FileCategory.TEXT_EXTRACTABLE == "text_extractable"
        assert FileCategory.UNSUPPORTED == "unsupported"

    def test_enum_from_string(self):
        assert FileCategory("directly_processable") == FileCategory.DIRECTLY_PROCESSABLE

    def test_enum_invalid_raises(self):
        with pytest.raises(ValueError):
            FileCategory("nonexistent")


class TestFileEntry:
    def test_create_minimal(self):
        entry = FileEntry(
            path=Path("/tmp/test.pdf"),
            name="test.pdf",
            stem="test",
            extension="pdf",
            size_bytes=1024,
            category=FileCategory.DIRECTLY_PROCESSABLE,
            parent_folder=Path("/tmp"),
        )
        assert entry.name == "test.pdf"
        assert entry.extension == "pdf"
        assert entry.is_symlink is False
        assert entry.skip_reason is None

    def test_symlink_entry(self):
        entry = FileEntry(
            path=Path("/tmp/link.txt"),
            name="link.txt",
            stem="link",
            extension="txt",
            size_bytes=100,
            category=FileCategory.TEXT_EXTRACTABLE,
            parent_folder=Path("/tmp"),
            is_symlink=True,
            symlink_target=Path("/tmp/real.txt"),
        )
        assert entry.is_symlink is True
        assert entry.symlink_target == Path("/tmp/real.txt")

    def test_with_skip_reason(self):
        entry = FileEntry(
            path=Path("/tmp/huge.zip"),
            name="huge.zip",
            stem="huge",
            extension="zip",
            size_bytes=3_000_000_000,
            category=FileCategory.UNSUPPORTED,
            parent_folder=Path("/tmp"),
            skip_reason="File exceeds 2 GB limit",
        )
        assert entry.skip_reason is not None


class TestFileMetadata:
    def test_minimal(self):
        meta = FileMetadata(size_bytes=1024, size_human="1.0 KB")
        assert meta.size_bytes == 1024
        assert meta.title is None
        assert meta.page_count is None

    def test_full_metadata(self):
        meta = FileMetadata(
            size_bytes=2048,
            size_human="2.0 KB",
            title="My Document",
            author="John Doe",
            page_count=10,
            created_at=datetime(2023, 1, 15),
            dimensions="1920x1080",
        )
        assert meta.title == "My Document"
        assert meta.author == "John Doe"
        assert meta.page_count == 10


class TestSymlinkEntry:
    def test_relative_symlink(self):
        entry = SymlinkEntry(
            symlink_path=Path("/tmp/link.txt"),
            target_path=Path("/tmp/real.txt"),
            is_relative=True,
        )
        assert entry.is_relative is True

    def test_absolute_symlink(self):
        entry = SymlinkEntry(
            symlink_path=Path("/tmp/link.txt"),
            target_path=Path("/other/real.txt"),
            is_relative=False,
        )
        assert entry.is_relative is False


class TestProposedRename:
    def test_create(self):
        rename = ProposedRename(
            current_name="IMG_001.jpg",
            proposed_name="sunset-beach.jpg",
            current_path=Path("/tmp/IMG_001.jpg"),
            proposed_path=Path("/tmp/sunset-beach.jpg"),
            reasoning="Photo of a sunset at the beach",
            confidence=0.95,
        )
        assert rename.is_unchanged is False
        assert rename.has_incoming_symlinks is False

    def test_unchanged_rename(self):
        rename = ProposedRename(
            current_name="good-name.pdf",
            proposed_name="good-name.pdf",
            current_path=Path("/tmp/good-name.pdf"),
            proposed_path=Path("/tmp/good-name.pdf"),
            reasoning="Already well-named",
            confidence=1.0,
            is_unchanged=True,
        )
        assert rename.is_unchanged is True


class TestContentSummary:
    def test_create(self):
        summary = ContentSummary(
            content_type="photograph",
            primary_subject="A sunset over the ocean",
            key_entities=["sunset", "ocean", "beach"],
            date_references=["2023-08-15"],
            language="en",
            confidence=0.95,
        )
        assert summary.content_type == "photograph"
        assert len(summary.key_entities) == 3


class TestExecutionResult:
    def test_create(self):
        result = ExecutionResult(
            run_id="20260226-abc12345",
            target_directory=Path("/tmp/test"),
            started_at=datetime.now(),
            total_files=10,
            renamed=8,
            skipped=1,
            failed=1,
            symlinks_updated=0,
            results=[],
        )
        assert result.renamed == 8
        assert result.estimated_cost_usd == 0.0


class TestImpactSummary:
    def test_create(self):
        summary = ImpactSummary(
            target_directory=Path("/tmp/test"),
            recursive=True,
            total_files=100,
            supported_files=90,
            unsupported_files=10,
            symlinks_found=2,
            symlink_targets_in_scope=1,
            folders_affected=5,
            deepest_nesting=3,
            estimated_api_calls=20,
            estimated_cost_usd=0.35,
            file_type_breakdown={"pdf": 50, "jpg": 30, "txt": 10},
            warnings=["Found 2 symlinks"],
        )
        assert summary.total_files == 100
        assert "pdf" in summary.file_type_breakdown


class TestDiscoveryResult:
    def test_create(self):
        result = DiscoveryResult(
            files=[],
            folders=[],
            symlink_map={},
            impact=ImpactSummary(
                target_directory=Path("/tmp"),
                recursive=False,
                total_files=0,
                supported_files=0,
                unsupported_files=0,
                symlinks_found=0,
                symlink_targets_in_scope=0,
                folders_affected=0,
                deepest_nesting=0,
                estimated_api_calls=0,
                estimated_cost_usd=0.0,
                file_type_breakdown={},
                warnings=[],
            ),
        )
        assert len(result.files) == 0


class TestModelSerialization:
    def test_file_entry_roundtrip(self):
        entry = FileEntry(
            path=Path("/tmp/test.pdf"),
            name="test.pdf",
            stem="test",
            extension="pdf",
            size_bytes=1024,
            category=FileCategory.DIRECTLY_PROCESSABLE,
            parent_folder=Path("/tmp"),
        )
        data = entry.model_dump()
        restored = FileEntry(**data)
        assert restored.name == entry.name
        assert restored.category == entry.category
