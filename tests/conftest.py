"""Shared pytest fixtures for ai-file-rename tests."""

import os
import tempfile
import shutil
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample-files"


@pytest.fixture
def fixtures_dir():
    """Return the path to the sample-files fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def temp_dir():
    """Create a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp(prefix="ai-rename-test-")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_dir_with_files(temp_dir):
    """Create a temp directory populated with a few test files."""
    # Create some simple test files
    (temp_dir / "report.pdf").write_bytes(b"%PDF-1.4 fake pdf content")
    (temp_dir / "IMG_001.jpg").write_bytes(
        b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JPEG header
    )
    (temp_dir / "notes.txt").write_text("Meeting notes from Q3 planning session.")
    (temp_dir / "download(1).pdf").write_bytes(b"%PDF-1.4 another fake pdf")
    (temp_dir / "Untitled.docx").write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    return temp_dir


@pytest.fixture
def temp_dir_with_symlinks(temp_dir):
    """Create a temp directory with symlinks for testing."""
    real_file = temp_dir / "real-file.txt"
    real_file.write_text("This is the real file content.")

    # Relative symlink
    rel_link = temp_dir / "relative-link.txt"
    os.symlink("real-file.txt", str(rel_link))

    # Another relative symlink
    another_link = temp_dir / "another-link.txt"
    os.symlink("real-file.txt", str(another_link))

    return temp_dir


@pytest.fixture
def temp_dir_nested(temp_dir):
    """Create a temp directory with nested subdirectories."""
    # Root level files
    (temp_dir / "root-file.txt").write_text("Root level document.")

    # Level 1
    level1 = temp_dir / "subdir1"
    level1.mkdir()
    (level1 / "level1-doc.pdf").write_bytes(b"%PDF-1.4 level 1 pdf")
    (level1 / "level1-img.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)

    # Level 2
    level2 = level1 / "deeper"
    level2.mkdir()
    (level2 / "level2-notes.txt").write_text("Deep level notes.")

    # Level 3
    level3 = level2 / "deepest"
    level3.mkdir()
    (level3 / "level3-data.csv").write_text("col1,col2\n1,2\n3,4\n")

    return temp_dir


@pytest.fixture
def mock_config():
    """Return a minimal Config object for testing."""
    from ai_file_rename.config import Config

    return Config(
        gemini_api_key="test-api-key-not-real",
        model="gemini-2.5-flash",
        max_files=500,
        cost_limit=5.00,
        require_confirmation=False,
    )
