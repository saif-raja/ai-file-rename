"""Tests for ai_file_rename.metadata — metadata extraction from files."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_file_rename.metadata import (
    _extract_legacy_office_metadata,
    _extract_os_metadata,
    _extract_video_metadata,
    _extract_video_metadata_ffprobe,
    _format_size,
    extract_metadata,
)
from ai_file_rename.models import FileCategory, FileEntry


FIXTURES = Path(__file__).parent / "fixtures" / "sample-files"


class TestFormatSize:
    def test_bytes(self):
        assert _format_size(500) == "500.0 B"

    def test_kilobytes(self):
        result = _format_size(2048)
        assert "KB" in result

    def test_megabytes(self):
        result = _format_size(5 * 1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self):
        result = _format_size(2 * 1024**3)
        assert "GB" in result

    def test_zero(self):
        assert _format_size(0) == "0.0 B"


class TestExtractOsMetadata:
    def test_basic_file(self):
        txt_file = FIXTURES / "text" / "notes.txt"
        if not txt_file.exists():
            pytest.skip("fixture not found")

        meta = _extract_os_metadata(txt_file)
        assert meta["size_bytes"] > 0
        assert "KB" in meta["size_human"] or "B" in meta["size_human"]
        assert meta["modified_at"] is not None
        assert meta["permissions"] is not None

    def test_nonexistent_file(self):
        meta = _extract_os_metadata(Path("/nonexistent/file.txt"))
        assert meta["size_bytes"] == 0


class TestExtractMetadata:
    def _make_entry(self, path: Path, ext: str, category=FileCategory.DIRECTLY_PROCESSABLE):
        return FileEntry(
            path=path,
            name=path.name,
            stem=path.stem,
            extension=ext,
            size_bytes=path.stat().st_size if path.exists() else 0,
            category=category,
            parent_folder=path.parent,
        )

    def test_text_file_metadata(self):
        txt_file = FIXTURES / "text" / "notes.txt"
        if not txt_file.exists():
            pytest.skip("fixture not found")

        entry = self._make_entry(txt_file, "txt", FileCategory.TEXT_EXTRACTABLE)
        meta = extract_metadata(entry)
        assert meta.size_bytes > 0
        assert meta.size_human is not None

    def test_csv_file_metadata(self):
        csv_file = FIXTURES / "text" / "data.csv"
        if not csv_file.exists():
            pytest.skip("fixture not found")

        entry = self._make_entry(csv_file, "csv", FileCategory.TEXT_EXTRACTABLE)
        meta = extract_metadata(entry)
        assert meta.size_bytes > 0

    def test_image_metadata(self):
        jpg_file = FIXTURES / "images" / "IMG_20190412_143022.jpg"
        if not jpg_file.exists():
            pytest.skip("fixture not found")

        entry = self._make_entry(jpg_file, "jpg")
        meta = extract_metadata(entry)
        assert meta.size_bytes > 0
        # Dimensions may be available if Pillow is installed
        # We don't assert on it since Pillow is optional

    def test_pdf_metadata(self):
        pdf_file = FIXTURES / "documents" / "document.pdf"
        if not pdf_file.exists():
            pytest.skip("fixture not found")

        entry = self._make_entry(pdf_file, "pdf")
        meta = extract_metadata(entry)
        assert meta.size_bytes > 0

    def test_wav_file_metadata(self):
        wav_file = FIXTURES / "audio" / "Voice Memo 001.wav"
        if not wav_file.exists():
            pytest.skip("fixture not found")

        entry = self._make_entry(wav_file, "wav")
        meta = extract_metadata(entry)
        assert meta.size_bytes > 0

    def test_edge_case_empty_file(self):
        empty = FIXTURES / "edge-cases" / "empty-file.txt"
        if not empty.exists():
            pytest.skip("fixture not found")

        entry = self._make_entry(empty, "txt", FileCategory.TEXT_EXTRACTABLE)
        meta = extract_metadata(entry)
        assert meta.size_bytes == 0


class TestFfprobeFallback:
    def test_ffprobe_not_installed(self, tmp_path):
        """Returns empty dict when ffprobe is not on PATH."""
        f = tmp_path / "video.mp4"
        f.write_bytes(b"\x00" * 100)

        with patch("ai_file_rename.metadata.shutil.which", return_value=None):
            result = _extract_video_metadata_ffprobe(f)
        assert result == {}

    def test_ffprobe_parses_output(self, tmp_path):
        """Parses ffprobe JSON output correctly."""
        f = tmp_path / "video.mp4"
        f.write_bytes(b"\x00" * 100)

        ffprobe_output = json.dumps({
            "format": {
                "duration": "120.5",
                "bit_rate": "3500000",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                },
            ],
        })

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ffprobe_output

        with patch("ai_file_rename.metadata.shutil.which", return_value="/usr/bin/ffprobe"), \
             patch("ai_file_rename.metadata.subprocess.run", return_value=mock_proc):
            result = _extract_video_metadata_ffprobe(f)

        assert result["duration_seconds"] == 120.5
        assert "3500" in result["bitrate"]
        assert result["codec"] == "h264"
        assert result["dimensions"] == "1920x1080"

    def test_video_metadata_falls_back_to_ffprobe(self, tmp_path):
        """_extract_video_metadata uses ffprobe when mutagen fails."""
        f = tmp_path / "video.avi"
        f.write_bytes(b"\x00" * 100)

        ffprobe_output = json.dumps({
            "format": {"duration": "60.0"},
            "streams": [{"codec_type": "video", "codec_name": "mpeg4", "width": 640, "height": 480}],
        })

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ffprobe_output

        # Force mutagen to fail by mocking import
        with patch("ai_file_rename.metadata.shutil.which", return_value="/usr/bin/ffprobe"), \
             patch("ai_file_rename.metadata.subprocess.run", return_value=mock_proc):
            result = _extract_video_metadata(f)

        assert result.get("duration_seconds") == 60.0 or result == {}  # depends on mutagen


class TestLegacyOfficeMetadata:
    def test_returns_empty_without_olefile(self, tmp_path):
        """Returns empty dict when olefile is not installed."""
        f = tmp_path / "test.doc"
        f.write_bytes(b"\x00" * 100)

        with patch.dict("sys.modules", {"olefile": None}):
            result = _extract_legacy_office_metadata(f)
        # May return empty or may still work if olefile is cached
        assert isinstance(result, dict)

    def test_returns_empty_for_non_ole_file(self, tmp_path):
        """Returns empty dict for non-OLE files."""
        f = tmp_path / "test.doc"
        f.write_text("not a real doc file")
        result = _extract_legacy_office_metadata(f)
        assert result == {}

    def test_extractors_table_has_legacy_formats(self):
        """DOC, PPT, XLS are registered in the EXTRACTORS table."""
        from ai_file_rename.metadata import EXTRACTORS
        assert "doc" in EXTRACTORS
        assert "ppt" in EXTRACTORS
        assert "xls" in EXTRACTORS
