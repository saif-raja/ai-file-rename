"""Tests for ai_file_rename.discovery — file system scanning and inventory."""

import os
from pathlib import Path

import pytest

from ai_file_rename.config import Config
from ai_file_rename.context import _build_breadcrumb, _calculate_depth
from ai_file_rename.discovery import (
    _classify_file,
    _is_excluded,
    build_symlink_map,
    discover,
)
from ai_file_rename.models import FileCategory


FIXTURES = Path(__file__).parent / "fixtures" / "sample-files"


@pytest.fixture
def config():
    return Config(gemini_api_key="test", max_files=500)


class TestClassifyFile:
    def test_jpeg_directly_processable(self):
        assert _classify_file("jpg") == FileCategory.DIRECTLY_PROCESSABLE

    def test_pdf_directly_processable(self):
        assert _classify_file("pdf") == FileCategory.DIRECTLY_PROCESSABLE

    def test_mp3_directly_processable(self):
        assert _classify_file("mp3") == FileCategory.DIRECTLY_PROCESSABLE

    def test_docx_convertible(self):
        assert _classify_file("docx") == FileCategory.CONVERTIBLE

    def test_svg_convertible(self):
        assert _classify_file("svg") == FileCategory.CONVERTIBLE

    def test_txt_text_extractable(self):
        assert _classify_file("txt") == FileCategory.TEXT_EXTRACTABLE

    def test_py_text_extractable(self):
        assert _classify_file("py") == FileCategory.TEXT_EXTRACTABLE

    def test_csv_text_extractable(self):
        assert _classify_file("csv") == FileCategory.TEXT_EXTRACTABLE

    def test_zip_unsupported(self):
        assert _classify_file("zip") == FileCategory.UNSUPPORTED

    def test_exe_unsupported(self):
        assert _classify_file("exe") == FileCategory.UNSUPPORTED

    def test_unknown_extension_unsupported(self):
        assert _classify_file("xyz123") == FileCategory.UNSUPPORTED

    def test_case_insensitive(self):
        assert _classify_file("PDF") == FileCategory.DIRECTLY_PROCESSABLE
        assert _classify_file("Jpg") == FileCategory.DIRECTLY_PROCESSABLE


class TestIsExcluded:
    def test_hidden_file_excluded(self):
        assert _is_excluded(Path(".hidden"), [".*"]) is True

    def test_tmp_file_excluded(self):
        assert _is_excluded(Path("file.tmp"), ["*.tmp"]) is True

    def test_git_excluded(self):
        assert _is_excluded(Path(".git"), [".git"]) is True

    def test_normal_file_not_excluded(self):
        assert _is_excluded(Path("report.pdf"), [".*", "*.tmp"]) is False


class TestBuildBreadcrumb:
    def test_root_folder(self):
        root = Path("/Users/test/documents")
        folder = Path("/Users/test/documents")
        result = _build_breadcrumb(folder, root)
        assert result == "documents"

    def test_one_level_deep(self):
        root = Path("/Users/test/documents")
        folder = Path("/Users/test/documents/research")
        result = _build_breadcrumb(folder, root)
        assert "documents" in result
        assert "research" in result

    def test_multiple_levels(self):
        root = Path("/Users/test/docs")
        folder = Path("/Users/test/docs/work/2023/q3")
        result = _build_breadcrumb(folder, root)
        assert "docs" in result
        assert "work" in result
        assert "2023" in result
        assert "q3" in result


class TestCalculateDepth:
    def test_root_depth_zero(self):
        root = Path("/tmp/test")
        assert _calculate_depth(root, root) == 0

    def test_depth_one(self):
        root = Path("/tmp/test")
        child = Path("/tmp/test/subdir")
        assert _calculate_depth(child, root) == 1

    def test_depth_three(self):
        root = Path("/tmp/test")
        deep = Path("/tmp/test/a/b/c")
        assert _calculate_depth(deep, root) == 3


class TestDiscoverFixtures:
    """Tests using the actual fixture directory."""

    def test_discover_single_folder(self, config):
        result = discover(FIXTURES / "images", recursive=False, config=config)
        assert result.impact.total_files > 0
        assert result.impact.folders_affected >= 1

    def test_discover_recursive(self, config):
        result = discover(FIXTURES, recursive=True, config=config)
        assert result.impact.total_files > 30
        assert result.impact.folders_affected > 5

    def test_discover_classifies_supported(self, config):
        result = discover(FIXTURES, recursive=True, config=config)
        assert result.impact.supported_files > 0
        assert result.impact.unsupported_files > 0

    def test_discover_detects_symlinks(self, config):
        result = discover(FIXTURES / "symlinks", recursive=False, config=config)
        assert result.impact.symlinks_found >= 2

    def test_discover_file_type_breakdown(self, config):
        result = discover(FIXTURES, recursive=True, config=config)
        assert "txt" in result.impact.file_type_breakdown
        assert "jpg" in result.impact.file_type_breakdown
        assert "pdf" in result.impact.file_type_breakdown

    def test_discover_nested_depth(self, config):
        result = discover(FIXTURES / "nested", recursive=True, config=config)
        assert result.impact.deepest_nesting >= 3

    def test_discover_nonexistent_raises(self, config):
        with pytest.raises(FileNotFoundError):
            discover(Path("/nonexistent/path"), recursive=False, config=config)

    def test_discover_file_not_dir_raises(self, config):
        with pytest.raises(NotADirectoryError):
            discover(FIXTURES / "text" / "notes.txt", recursive=False, config=config)

    def test_discover_respects_max_files(self):
        config = Config(gemini_api_key="test", max_files=5)
        result = discover(FIXTURES, recursive=True, config=config)
        assert len(result.files) <= 5

    def test_discover_unsupported_files(self, config):
        result = discover(FIXTURES / "unsupported", recursive=False, config=config)
        for f in result.files:
            assert f.category == FileCategory.UNSUPPORTED

    def test_discover_text_files(self, config):
        result = discover(FIXTURES / "text", recursive=False, config=config)
        for f in result.files:
            assert f.category in (
                FileCategory.TEXT_EXTRACTABLE,
                FileCategory.DIRECTLY_PROCESSABLE,
            )

    def test_discover_edge_cases(self, config):
        result = discover(FIXTURES / "edge-cases", recursive=False, config=config)
        names = [f.name for f in result.files]
        # Should find at least the non-hidden edge case files
        assert len(result.files) > 0


class TestBuildSymlinkMap:
    def test_symlink_map_from_fixtures(self):
        symlink_dir = FIXTURES / "symlinks"
        if not symlink_dir.exists():
            pytest.skip("symlinks fixture not found")

        smap = build_symlink_map(symlink_dir, recursive=False)
        # real-file.txt should have at least one symlink pointing to it
        real_path = str((symlink_dir / "real-file.txt").resolve())
        assert real_path in smap
        assert len(smap[real_path]) >= 1

    def test_symlink_map_records_relative(self):
        symlink_dir = FIXTURES / "symlinks"
        if not symlink_dir.exists():
            pytest.skip("symlinks fixture not found")

        smap = build_symlink_map(symlink_dir, recursive=False)
        real_path = str((symlink_dir / "real-file.txt").resolve())
        if real_path in smap:
            # Our fixture symlinks should be relative
            for entry in smap[real_path]:
                assert entry.is_relative is True


class TestDiscoverWithTempDir:
    """Tests using temporary directories for isolation."""

    def test_discover_empty_dir(self, config, temp_dir):
        result = discover(temp_dir, recursive=False, config=config)
        assert result.impact.total_files == 0

    def test_discover_with_files(self, config, temp_dir_with_files):
        result = discover(temp_dir_with_files, recursive=False, config=config)
        assert result.impact.total_files >= 4
        names = [f.name for f in result.files]
        assert "report.pdf" in names
        assert "notes.txt" in names
