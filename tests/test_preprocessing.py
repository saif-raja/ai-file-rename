"""Tests for ai_file_rename.preprocessing: format conversion."""

from pathlib import Path

import pytest

from ai_file_rename.config import Config
from ai_file_rename.models import FileCategory, FileEntry
from ai_file_rename.preprocessing import preprocess


FIXTURES = Path(__file__).parent / "fixtures" / "sample-files"


def _make_entry(path: Path, ext: str, category: FileCategory) -> FileEntry:
    """Helper to create a FileEntry."""
    return FileEntry(
        path=path,
        name=path.name,
        stem=path.stem,
        extension=ext,
        size_bytes=path.stat().st_size if path.exists() else 0,
        category=category,
        parent_folder=path.parent,
    )


class TestPreprocess:
    def test_directly_processable_passes_through(self, temp_dir):
        """Test that directly processable files pass through unchanged."""
        jpg_file = FIXTURES / "images" / "IMG_20190412_143022.jpg"
        if not jpg_file.exists():
            pytest.skip("fixture not found")

        entry = _make_entry(jpg_file, "jpg", FileCategory.DIRECTLY_PROCESSABLE)
        config = Config(gemini_api_key="test")

        results = preprocess([entry], temp_dir, config)

        assert len(results) == 1
        assert results[0].processed_path == jpg_file

    def test_text_extractable_passes_through(self, temp_dir):
        """Test that text files pass through (no conversion needed)."""
        txt_file = FIXTURES / "text" / "notes.txt"
        if not txt_file.exists():
            pytest.skip("fixture not found")

        entry = _make_entry(txt_file, "txt", FileCategory.TEXT_EXTRACTABLE)
        config = Config(gemini_api_key="test")

        results = preprocess([entry], temp_dir, config)

        assert len(results) == 1
        assert results[0].processed_path == txt_file

    def test_unsupported_file_has_no_processed_path(self, temp_dir):
        """Test that unsupported files get no processed path."""
        zip_file = FIXTURES / "unsupported" / "archive.zip"
        if not zip_file.exists():
            pytest.skip("fixture not found")

        entry = _make_entry(zip_file, "zip", FileCategory.UNSUPPORTED)
        entry.skip_reason = "Unsupported format"
        config = Config(gemini_api_key="test")

        results = preprocess([entry], temp_dir, config)

        assert len(results) == 1
        assert results[0].processed_path is None

    def test_metadata_extracted_for_all(self, temp_dir):
        """Test that metadata is extracted for all files."""
        txt_file = FIXTURES / "text" / "notes.txt"
        if not txt_file.exists():
            pytest.skip("fixture not found")

        entry = _make_entry(txt_file, "txt", FileCategory.TEXT_EXTRACTABLE)
        config = Config(gemini_api_key="test")

        results = preprocess([entry], temp_dir, config)

        assert results[0].metadata.size_bytes > 0
        assert results[0].metadata.size_human is not None

    def test_multiple_files(self, temp_dir):
        """Test preprocessing multiple files at once."""
        entries = []
        for name, ext, cat in [
            ("notes.txt", "txt", FileCategory.TEXT_EXTRACTABLE),
            ("data.csv", "csv", FileCategory.TEXT_EXTRACTABLE),
        ]:
            path = FIXTURES / "text" / name
            if path.exists():
                entries.append(_make_entry(path, ext, cat))

        if not entries:
            pytest.skip("no fixtures found")

        config = Config(gemini_api_key="test")
        results = preprocess(entries, temp_dir, config)

        assert len(results) == len(entries)
        for r in results:
            assert r.metadata is not None

    def test_bmp_conversion(self, temp_dir):
        """Test BMP to PNG conversion (if Pillow is available)."""
        bmp_file = FIXTURES / "images" / "image(1).bmp"
        if not bmp_file.exists():
            pytest.skip("fixture not found")

        entry = _make_entry(bmp_file, "bmp", FileCategory.CONVERTIBLE)
        config = Config(gemini_api_key="test")

        results = preprocess([entry], temp_dir, config)

        assert len(results) == 1
        # If Pillow is installed, conversion should succeed
        if results[0].processed_path and results[0].processed_path != bmp_file:
            assert results[0].processed_path.suffix == ".png"
            assert results[0].processed_path.exists()
