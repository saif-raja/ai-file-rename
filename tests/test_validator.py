"""Tests for ai_file_rename.validator — name validation, sanitization, collision resolution."""

from pathlib import Path

import pytest

from ai_file_rename.models import ProposedRename, SymlinkEntry
from ai_file_rename.validator import (
    check_existing_collisions,
    is_well_named,
    resolve_collisions,
    sanitize_and_build_name,
    sanitize_name,
    truncate_name,
    validate_renames,
)


class TestSanitizeName:
    """Test cross-platform name sanitization."""

    def test_lowercase(self):
        assert sanitize_name("MyDocument") == "mydocument"

    def test_spaces_to_hyphens(self):
        assert sanitize_name("my document name") == "my-document-name"

    def test_underscores_to_hyphens(self):
        assert sanitize_name("my_document_name") == "my-document-name"

    def test_forbidden_chars_removed(self):
        result = sanitize_name('file<with>bad:chars')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result

    def test_unicode_transliteration(self):
        result = sanitize_name("café-résumé")
        assert result == "cafe-resume"

    def test_collapse_multiple_hyphens(self):
        assert sanitize_name("a---b---c") == "a-b-c"

    def test_strip_leading_trailing_hyphens(self):
        assert sanitize_name("---hello---") == "hello"

    def test_strip_leading_trailing_dots(self):
        assert sanitize_name("...hello...") == "hello"

    def test_windows_reserved_name_con(self):
        result = sanitize_name("CON")
        assert result.startswith("file-")
        assert "con" in result

    def test_windows_reserved_name_prn(self):
        result = sanitize_name("PRN")
        assert result.startswith("file-")

    def test_windows_reserved_name_nul(self):
        result = sanitize_name("NUL")
        assert result.startswith("file-")

    def test_windows_reserved_com_ports(self):
        for i in range(1, 10):
            result = sanitize_name(f"COM{i}")
            assert result.startswith("file-")

    def test_windows_reserved_lpt_ports(self):
        for i in range(1, 10):
            result = sanitize_name(f"LPT{i}")
            assert result.startswith("file-")

    def test_leading_dot_prevented(self):
        result = sanitize_name(".hidden")
        assert not result.startswith(".")

    def test_empty_string_fallback(self):
        result = sanitize_name("")
        assert result == "unnamed-file"

    def test_all_forbidden_chars_fallback(self):
        result = sanitize_name(':::""<>')
        assert result == "unnamed-file"

    def test_pipe_and_question_mark(self):
        result = sanitize_name("file|name?here")
        assert "|" not in result
        assert "?" not in result

    def test_control_chars_removed(self):
        result = sanitize_name("file\x00name\x1fhere")
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_mixed_separators(self):
        result = sanitize_name("my file_name-here")
        assert result == "my-file-name-here"

    def test_already_clean_name(self):
        assert sanitize_name("clean-name") == "clean-name"

    def test_uber_transliteration(self):
        result = sanitize_name("über")
        assert result == "uber"


class TestTruncateName:
    def test_no_truncation_needed(self):
        result = truncate_name("short-name", "pdf", max_length=200)
        assert result == "short-name"

    def test_truncation_at_word_boundary(self):
        long_name = "this-is-a-very-long-file-name-that-should-be-truncated"
        result = truncate_name(long_name, "pdf", max_length=40)
        # Should truncate at a hyphen, not mid-word
        assert len(result) + 4 <= 40  # +4 for ".pdf"
        assert result.endswith("-") is False

    def test_max_length_respected(self):
        very_long = "word-" * 50  # 250 chars
        result = truncate_name(very_long, "txt", max_length=200)
        assert len(result) + 4 <= 200  # +4 for ".txt"


class TestResolveCollisions:
    def _make_rename(self, current: str, proposed: str) -> ProposedRename:
        return ProposedRename(
            current_name=current,
            proposed_name=proposed,
            current_path=Path(f"/tmp/{current}"),
            proposed_path=Path(f"/tmp/{proposed}"),
            reasoning="test",
            confidence=0.9,
        )

    def test_no_collisions(self):
        renames = [
            self._make_rename("a.pdf", "doc-one.pdf"),
            self._make_rename("b.pdf", "doc-two.pdf"),
        ]
        result = resolve_collisions(renames)
        assert result[0].proposed_name == "doc-one.pdf"
        assert result[1].proposed_name == "doc-two.pdf"

    def test_single_collision(self):
        renames = [
            self._make_rename("a.pdf", "report.pdf"),
            self._make_rename("b.pdf", "report.pdf"),
        ]
        result = resolve_collisions(renames)
        assert result[0].proposed_name == "report.pdf"
        assert result[1].proposed_name == "report-2.pdf"

    def test_triple_collision(self):
        renames = [
            self._make_rename("a.pdf", "report.pdf"),
            self._make_rename("b.pdf", "report.pdf"),
            self._make_rename("c.pdf", "report.pdf"),
        ]
        result = resolve_collisions(renames)
        assert result[0].proposed_name == "report.pdf"
        assert result[1].proposed_name == "report-2.pdf"
        assert result[2].proposed_name == "report-3.pdf"

    def test_case_insensitive_collision(self):
        renames = [
            self._make_rename("a.pdf", "Report.pdf"),
            self._make_rename("b.pdf", "report.pdf"),
        ]
        result = resolve_collisions(renames)
        # Second one should get a suffix
        assert result[1].proposed_name == "report-2.pdf"


class TestCheckExistingCollisions:
    def _make_rename(self, current: str, proposed: str) -> ProposedRename:
        return ProposedRename(
            current_name=current,
            proposed_name=proposed,
            current_path=Path(f"/tmp/{current}"),
            proposed_path=Path(f"/tmp/{proposed}"),
            reasoning="test",
            confidence=0.9,
        )

    def test_no_collision_with_existing(self):
        renames = [self._make_rename("a.pdf", "new-name.pdf")]
        existing = {"a.pdf", "other.pdf"}
        being_renamed = {"a.pdf"}
        result = check_existing_collisions(renames, existing, being_renamed)
        assert result[0].proposed_name == "new-name.pdf"

    def test_collision_with_existing(self):
        renames = [self._make_rename("a.pdf", "other.pdf")]
        existing = {"a.pdf", "other.pdf"}
        being_renamed = {"a.pdf"}
        result = check_existing_collisions(renames, existing, being_renamed)
        assert result[0].proposed_name == "other-2.pdf"


class TestIsWellNamed:
    def test_short_name_not_well_named(self):
        assert is_well_named("doc.pdf") is False

    def test_default_pattern_img(self):
        assert is_well_named("IMG_20190412_143022.jpg") is False

    def test_default_pattern_screenshot(self):
        assert is_well_named("Screenshot 2023-11-15 at 3.42.12 PM.png") is False

    def test_default_pattern_download(self):
        assert is_well_named("download(3).pdf") is False

    def test_default_pattern_untitled(self):
        assert is_well_named("Untitled document.docx") is False

    def test_hex_hash_name(self):
        assert is_well_named("a7f3b2c1d4e5.png") is False

    def test_uuid_name(self):
        assert is_well_named("550e8400-e29b-41d4-a716-446655440000.pdf") is False

    def test_well_named_descriptive(self):
        assert is_well_named("quarterly-revenue-report-2023.pdf") is True

    def test_well_named_descriptive_photo(self):
        assert is_well_named("sunset-over-golden-gate-bridge.jpg") is True

    def test_well_named_meeting_notes(self):
        assert is_well_named("meeting-notes-project-alpha.txt") is True


class TestValidateRenames:
    def _make_rename(self, current: str, proposed: str) -> ProposedRename:
        return ProposedRename(
            current_name=current,
            proposed_name=proposed,
            current_path=Path(f"/tmp/{current}"),
            proposed_path=Path(f"/tmp/{proposed}"),
            reasoning="test",
            confidence=0.9,
        )

    def test_basic_validation(self):
        renames = [self._make_rename("a.pdf", "clean-name.pdf")]
        result = validate_renames(renames)
        assert len(result) == 1
        assert result[0].final_name == "clean-name.pdf"

    def test_sanitization_applied(self):
        renames = [self._make_rename("a.pdf", "File With Spaces.pdf")]
        result = validate_renames(renames)
        assert " " not in result[0].final_name
        assert result[0].final_name == "file-with-spaces.pdf"

    def test_collision_resolution_in_validation(self):
        renames = [
            self._make_rename("a.pdf", "report.pdf"),
            self._make_rename("b.pdf", "report.pdf"),
        ]
        result = validate_renames(renames)
        names = {r.final_name for r in result}
        assert len(names) == 2  # No duplicates

    def test_symlink_planning(self):
        renames = [self._make_rename("a.pdf", "new-name.pdf")]
        symlink_map = {
            str(Path("/tmp/a.pdf")): [
                SymlinkEntry(
                    symlink_path=Path("/tmp/link.pdf"),
                    target_path=Path("/tmp/a.pdf"),
                    is_relative=True,
                )
            ]
        }
        result = validate_renames(renames, symlink_map=symlink_map)
        assert len(result[0].symlink_updates) == 1


class TestSanitizeAndBuildName:
    def test_with_extension(self):
        result = sanitize_and_build_name("My Document.pdf")
        assert result == "my-document.pdf"

    def test_without_extension(self):
        result = sanitize_and_build_name("noext")
        assert result == "noext"

    def test_unicode_full_name(self):
        result = sanitize_and_build_name("café-résumé.txt")
        assert result == "cafe-resume.txt"
