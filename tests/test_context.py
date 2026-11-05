"""Tests for ai_file_rename.context: folder context building."""

from pathlib import Path

import pytest

from ai_file_rename.config import Config
from ai_file_rename.context import build_context
from ai_file_rename.discovery import discover
from ai_file_rename.models import EnrichedFile, FileCategory, FileEntry, FileMetadata


FIXTURES = Path(__file__).parent / "fixtures" / "sample-files"


def _make_enriched(name: str, parent: Path, ext: str = "txt") -> EnrichedFile:
    """Helper to create an EnrichedFile for testing."""
    path = parent / name
    return EnrichedFile(
        entry=FileEntry(
            path=path,
            name=name,
            stem=Path(name).stem,
            extension=ext,
            size_bytes=100,
            category=FileCategory.TEXT_EXTRACTABLE,
            parent_folder=parent,
        ),
        metadata=FileMetadata(size_bytes=100, size_human="100 B"),
    )


class TestBuildContext:
    def test_single_folder(self):
        root = Path("/tmp/testdir")
        files = [
            _make_enriched("file1.txt", root),
            _make_enriched("file2.txt", root),
            _make_enriched("file3.txt", root),
        ]
        contexts = build_context(files, root)
        assert len(contexts) == 1
        ctx = list(contexts.values())[0]
        assert ctx.file_count == 3
        assert ctx.folder_name == "testdir"

    def test_multiple_folders(self):
        root = Path("/tmp/testdir")
        folder_a = root / "subdir_a"
        folder_b = root / "subdir_b"
        files = [
            _make_enriched("a1.txt", folder_a),
            _make_enriched("a2.txt", folder_a),
            _make_enriched("b1.txt", folder_b),
        ]
        contexts = build_context(files, root)
        assert len(contexts) == 2

    def test_breadcrumb_generation(self):
        root = Path("/tmp/docs")
        subdir = root / "research" / "ml"
        files = [_make_enriched("paper.txt", subdir)]
        contexts = build_context(files, root)
        ctx = contexts[subdir]
        assert "docs" in ctx.breadcrumb
        assert "research" in ctx.breadcrumb
        assert "ml" in ctx.breadcrumb

    def test_depth_calculation(self):
        root = Path("/tmp/docs")
        deep = root / "a" / "b" / "c"
        files = [_make_enriched("file.txt", deep)]
        contexts = build_context(files, root)
        ctx = contexts[deep]
        assert ctx.depth == 3

    def test_sibling_names_included(self):
        root = Path("/tmp/testdir")
        files = [
            _make_enriched("file1.txt", root),
            _make_enriched("file2.txt", root),
        ]
        contexts = build_context(files, root)
        ctx = list(contexts.values())[0]
        # Sibling names should include at least the files we added
        assert len(ctx.sibling_names) >= 2


class TestBuildContextWithFixtures:
    """Tests using actual fixture directory."""

    def test_context_from_text_fixtures(self):
        config = Config(gemini_api_key="test")
        result = discover(FIXTURES / "text", recursive=False, config=config)

        enriched = [
            EnrichedFile(
                entry=f,
                metadata=FileMetadata(
                    size_bytes=f.size_bytes,
                    size_human=f"{f.size_bytes} B",
                ),
            )
            for f in result.files
        ]

        contexts = build_context(enriched, FIXTURES / "text")
        assert len(contexts) >= 1

        for ctx in contexts.values():
            assert ctx.file_count > 0
            assert len(ctx.sibling_names) > 0

    def test_context_from_nested_fixtures(self):
        config = Config(gemini_api_key="test")
        result = discover(FIXTURES / "nested", recursive=True, config=config)

        enriched = [
            EnrichedFile(
                entry=f,
                metadata=FileMetadata(
                    size_bytes=f.size_bytes,
                    size_human=f"{f.size_bytes} B",
                ),
            )
            for f in result.files
        ]

        contexts = build_context(enriched, FIXTURES / "nested")
        # Should have multiple folders at different depths
        assert len(contexts) >= 2
        depths = {ctx.depth for ctx in contexts.values()}
        assert max(depths) >= 2
