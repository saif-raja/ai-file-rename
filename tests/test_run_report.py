"""Tests for RunReport stateful report and default exclude patterns."""

import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_file_rename.config import Config
from ai_file_rename.cli import RunReport
from ai_file_rename.models import (
    DiscoveryResult,
    ImpactSummary,
    ProposedRename,
    ValidatedRename,
)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="ai-rename-report-test-")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def _make_validated(current: str, proposed: str, unchanged: bool = False) -> ValidatedRename:
    return ValidatedRename(
        original=ProposedRename(
            current_name=current,
            proposed_name=proposed,
            current_path=Path(f"/tmp/{current}"),
            proposed_path=Path(f"/tmp/{proposed}"),
            reasoning="test reasoning",
            confidence=0.9,
            is_unchanged=unchanged,
        ),
        final_name=proposed,
        validation_notes=[],
    )


def _make_discovery(target: Path) -> DiscoveryResult:
    impact = ImpactSummary(
        target_directory=target,
        recursive=False,
        total_files=10,
        supported_files=8,
        unsupported_files=2,
        already_well_named=3,
        symlinks_found=0,
        symlink_targets_in_scope=0,
        folders_affected=1,
        deepest_nesting=0,
        estimated_api_calls=2,
        estimated_cost_usd=0.01,
        file_type_breakdown={"pdf": 5, "jpg": 3, "zip": 2},
        warnings=[],
    )
    return DiscoveryResult(
        files=[],
        folders=[],
        symlink_map={},
        impact=impact,
    )


def _make_report(temp_dir, run_id="20260228-abc12345"):
    """Create a RunReport with default config."""
    config = Config(gemini_api_key="test", model="gemini-2.5-flash")
    return RunReport(temp_dir, run_id, config)


class TestRunReportStateful:
    def test_creates_report_on_first_update(self, temp_dir):
        """Report file is created on the first update() call."""
        report = _make_report(temp_dir)
        report.update("starting")
        assert report.report_path.exists()

    def test_status_updates_in_file(self, temp_dir):
        """Each update() rewrites the file with the new status."""
        report = _make_report(temp_dir)

        report.update("starting")
        content = report.report_path.read_text()
        assert "**starting**" in content

        report.update("discovered", discovery=_make_discovery(temp_dir))
        content = report.report_path.read_text()
        assert "**discovered**" in content

    def test_same_file_throughout(self, temp_dir):
        """The same timestamped file is rewritten, not a new one."""
        report = _make_report(temp_dir, run_id="20260228-same0001")

        report.update("starting")
        report.update("discovered", discovery=_make_discovery(temp_dir))
        report.update("analyzing", analyzed_count=6)

        # Only one report file should exist
        reports = list(temp_dir.glob(".ai-rename-report-*.md"))
        assert len(reports) == 1
        assert reports[0].name == ".ai-rename-report-20260228-same0001.md"

    def test_timestamp_persists_across_updates(self, temp_dir):
        """The timestamp is set once at creation and doesn't change."""
        report = _make_report(temp_dir)
        original_timestamp = report.timestamp

        report.update("starting")
        report.update("discovered", discovery=_make_discovery(temp_dir))
        report.update("analyzing")

        content = report.report_path.read_text()
        assert original_timestamp in content

    def test_discovery_data_accumulates(self, temp_dir):
        """Discovery data persists across subsequent updates."""
        report = _make_report(temp_dir)
        discovery = _make_discovery(temp_dir)

        report.update("discovered", discovery=discovery)
        report.update("analyzing", analyzed_count=6)

        content = report.report_path.read_text()
        # Discovery data should still be present
        assert "Files discovered: 10" in content
        # And new data too
        assert "Files analyzed: 6" in content

    def test_proposed_renames_appear(self, temp_dir):
        """Validated renames appear in the report table."""
        report = _make_report(temp_dir)
        discovery = _make_discovery(temp_dir)
        validated = [
            _make_validated("IMG_001.jpg", "sunset-beach.jpg"),
            _make_validated("doc.pdf", "revenue-report.pdf"),
        ]

        report.update("discovered", discovery=discovery)
        report.update(
            "proposed",
            validated=validated,
            total_tokens={"input_tokens": 1000, "output_tokens": 500},
        )

        content = report.report_path.read_text()
        assert "IMG_001.jpg" in content
        assert "sunset-beach.jpg" in content
        assert "revenue-report.pdf" in content

    def test_dry_run_complete_status(self, temp_dir):
        """Dry-run completion shows correct status and mode."""
        report = _make_report(temp_dir)
        report.update("discovered", discovery=_make_discovery(temp_dir))
        report.update(
            "proposed",
            validated=[_make_validated("a.txt", "alpha.txt")],
            total_tokens={"input_tokens": 100, "output_tokens": 50},
        )
        report.update("dry-run-complete")

        content = report.report_path.read_text()
        assert "**dry-run-complete**" in content
        assert "**dry-run**" in content  # mode field

    def test_executed_status(self, temp_dir):
        """Executed run shows correct status and execution results."""
        report = _make_report(temp_dir)
        report.update("discovered", discovery=_make_discovery(temp_dir))
        report.update(
            "proposed",
            validated=[_make_validated("a.txt", "alpha.txt")],
            total_tokens={"input_tokens": 100, "output_tokens": 50},
        )

        mock_result = MagicMock()
        mock_result.renamed = 1
        mock_result.skipped = 0
        mock_result.failed = 0
        mock_result.symlinks_updated = 0

        report.update("completed", executed=True, result=mock_result)

        content = report.report_path.read_text()
        assert "**completed**" in content
        assert "**executed**" in content  # mode field
        assert "Files renamed: 1" in content

    def test_well_named_section(self, temp_dir):
        """Well-named files appear when set."""
        report = _make_report(temp_dir)
        report.update("discovered", discovery=_make_discovery(temp_dir))
        report.update(
            "analyzing",
            skipped_well_named=["quarterly-revenue-report.pdf", "meeting-notes-alpha.txt"],
            analyzed_count=4,
        )

        content = report.report_path.read_text()
        assert "quarterly-revenue-report.pdf" in content
        assert "meeting-notes-alpha.txt" in content

    def test_analysis_failures_section(self, temp_dir):
        """Analysis failures appear when set."""
        report = _make_report(temp_dir)
        report.update("discovered", discovery=_make_discovery(temp_dir))
        report.update(
            "proposed",
            validated=[_make_validated("a.txt", "alpha.txt")],
            total_tokens={"input_tokens": 100, "output_tokens": 50},
            analysis_failures=[
                ("video.mov", "400 FAILED_PRECONDITION"),
                ("corrupt.pdf", "Unable to read file"),
            ],
        )

        content = report.report_path.read_text()
        assert "video.mov" in content
        assert "400 FAILED_PRECONDITION" in content

    def test_report_filenames_dont_collide(self, temp_dir):
        """Different run IDs produce different report files."""
        r1 = _make_report(temp_dir, "20260228-run00001")
        r2 = _make_report(temp_dir, "20260228-run00002")

        r1.update("starting")
        r2.update("starting")

        assert (temp_dir / ".ai-rename-report-20260228-run00001.md").exists()
        assert (temp_dir / ".ai-rename-report-20260228-run00002.md").exists()

    def test_update_is_non_fatal(self, temp_dir):
        """If the write fails (e.g. bad path), update() doesn't raise."""
        config = Config(gemini_api_key="test")
        report = RunReport(Path("/nonexistent/impossible/path"), "test-id", config)
        # Should not raise
        report.update("starting")


class TestDefaultExcludePatterns:
    def test_report_files_excluded_by_default(self):
        """ai-rename report files are in the default exclude patterns."""
        config = Config(gemini_api_key="test")
        assert any(
            ".ai-rename-report" in p for p in config.exclude_patterns
        )

    def test_manifest_excluded_by_default(self):
        """ai-rename manifest files are in the default exclude patterns."""
        config = Config(gemini_api_key="test")
        assert any(
            ".ai-rename-manifest" in p for p in config.exclude_patterns
        )

    def test_dotfiles_excluded_by_default(self):
        """Dotfiles are excluded by default via '.*' pattern."""
        config = Config(gemini_api_key="test")
        assert ".*" in config.exclude_patterns

    def test_report_matched_by_fnmatch(self):
        """The report filename is actually matched by the exclude patterns."""
        import fnmatch

        config = Config(gemini_api_key="test")
        report_name = ".ai-rename-report-20260228-abc12345.md"

        matched = any(
            fnmatch.fnmatch(report_name, pattern)
            for pattern in config.exclude_patterns
        )
        assert matched, f"Report file '{report_name}' not matched by any exclude pattern"
