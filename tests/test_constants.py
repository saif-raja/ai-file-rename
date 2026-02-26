"""Tests for ai_file_rename.constants — format maps, naming rules, prompts."""

import re

import pytest

from ai_file_rename.constants import (
    API_LIMITS,
    CONTENT_ANALYSIS_PROMPT,
    CONVERSION_MAP,
    COST_PER_TOKEN,
    DEFAULT_PATTERNS,
    FORMAT_CATEGORIES,
    HOLISTIC_NAMING_PROMPT,
    METADATA_EXTRACTORS_MAP,
    MIME_TYPE_MAP,
    NAMING_RULES,
)


class TestFormatCategories:
    def test_jpeg_is_processable(self):
        assert FORMAT_CATEGORIES["jpeg"] == "directly_processable"
        assert FORMAT_CATEGORIES["jpg"] == "directly_processable"

    def test_pdf_is_processable(self):
        assert FORMAT_CATEGORIES["pdf"] == "directly_processable"

    def test_docx_is_convertible(self):
        assert FORMAT_CATEGORIES["docx"] == "convertible"

    def test_svg_is_convertible(self):
        assert FORMAT_CATEGORIES["svg"] == "convertible"

    def test_txt_is_text_extractable(self):
        assert FORMAT_CATEGORIES["txt"] == "text_extractable"

    def test_zip_is_unsupported(self):
        assert FORMAT_CATEGORIES["zip"] == "unsupported"

    def test_all_extensions_lowercase(self):
        for ext in FORMAT_CATEGORIES:
            assert ext == ext.lower(), f"Extension '{ext}' should be lowercase"

    def test_no_leading_dots(self):
        for ext in FORMAT_CATEGORIES:
            assert not ext.startswith("."), f"Extension '{ext}' should not start with dot"


class TestMimeTypeMap:
    def test_jpeg_mime(self):
        assert MIME_TYPE_MAP["jpg"] == "image/jpeg"

    def test_pdf_mime(self):
        assert MIME_TYPE_MAP["pdf"] == "application/pdf"

    def test_mp3_mime(self):
        assert MIME_TYPE_MAP["mp3"] == "audio/mpeg"

    def test_mp4_mime(self):
        assert MIME_TYPE_MAP["mp4"] == "video/mp4"

    def test_all_processable_have_mime(self):
        """Every directly processable format should have a MIME type."""
        for ext, cat in FORMAT_CATEGORIES.items():
            if cat == "directly_processable":
                assert ext in MIME_TYPE_MAP, f"No MIME type for '{ext}'"


class TestConversionMap:
    def test_svg_converts_to_png(self):
        target, _ = CONVERSION_MAP["svg"]
        assert target == "png"

    def test_docx_converts_to_pdf(self):
        target, _ = CONVERSION_MAP["docx"]
        assert target == "pdf"

    def test_all_convertible_have_mapping(self):
        """Every convertible format should have a conversion mapping."""
        for ext, cat in FORMAT_CATEGORIES.items():
            if cat == "convertible":
                assert ext in CONVERSION_MAP, f"No conversion mapping for '{ext}'"


class TestNamingRules:
    def test_max_length(self):
        assert NAMING_RULES["max_name_length"] == 200

    def test_separator(self):
        assert NAMING_RULES["separator"] == "-"

    def test_min_words(self):
        assert NAMING_RULES["min_words"] == 2

    def test_max_words(self):
        assert NAMING_RULES["max_words"] == 8

    def test_forbidden_chars_regex_valid(self):
        pattern = NAMING_RULES["forbidden_chars_pattern"]
        regex = re.compile(pattern)
        # Should match forbidden chars
        assert regex.search("<") is not None
        assert regex.search(">") is not None
        assert regex.search(":") is not None
        assert regex.search('"') is not None
        assert regex.search("?") is not None
        assert regex.search("*") is not None
        # Should NOT match normal chars
        assert regex.search("a") is None
        assert regex.search("-") is None

    def test_windows_reserved_names(self):
        reserved = NAMING_RULES["windows_reserved_names"]
        assert "CON" in reserved
        assert "PRN" in reserved
        assert "NUL" in reserved
        assert "COM1" in reserved
        assert "LPT1" in reserved


class TestDefaultPatterns:
    def test_img_pattern_matches(self):
        for pattern in DEFAULT_PATTERNS:
            if "IMG" in pattern:
                assert re.search(pattern, "IMG_20190412", re.IGNORECASE)
                break

    def test_screenshot_pattern_matches(self):
        matched = False
        for pattern in DEFAULT_PATTERNS:
            if re.search(pattern, "Screenshot 2023", re.IGNORECASE):
                matched = True
                break
        assert matched

    def test_uuid_pattern_matches(self):
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        matched = False
        for pattern in DEFAULT_PATTERNS:
            if re.search(pattern, uuid, re.IGNORECASE):
                matched = True
                break
        assert matched

    def test_download_pattern_matches(self):
        matched = False
        for pattern in DEFAULT_PATTERNS:
            if re.search(pattern, "download", re.IGNORECASE):
                matched = True
                break
        assert matched


class TestContentAnalysisPrompt:
    def test_contains_all_placeholders(self):
        expected_placeholders = [
            "full_path",
            "parent_folder_name",
            "breadcrumb_path",
            "current_filename",
            "mime_type",
            "file_size_human_readable",
            "created_date",
            "modified_date",
            "accessed_date",
            "is_symlink",
            "symlink_target",
            "embedded_metadata_json",
        ]
        for placeholder in expected_placeholders:
            assert f"{{{placeholder}}}" in CONTENT_ANALYSIS_PROMPT, (
                f"Missing placeholder: {placeholder}"
            )

    def test_json_format_in_prompt(self):
        assert "content_type" in CONTENT_ANALYSIS_PROMPT
        assert "primary_subject" in CONTENT_ANALYSIS_PROMPT
        assert "key_entities" in CONTENT_ANALYSIS_PROMPT
        assert "confidence" in CONTENT_ANALYSIS_PROMPT

    def test_prompt_can_be_formatted(self):
        """Test that the prompt can be formatted without errors."""
        result = CONTENT_ANALYSIS_PROMPT.format(
            full_path="/tmp/test.pdf",
            parent_folder_name="docs",
            breadcrumb_path="docs > research",
            current_filename="test.pdf",
            mime_type="application/pdf",
            file_size_human_readable="4.2 MB",
            created_date="2023-01-15",
            modified_date="2023-01-20",
            accessed_date="2024-01-01",
            is_symlink="false",
            symlink_target="N/A",
            embedded_metadata_json="null",
        )
        assert "test.pdf" in result


class TestHolisticNamingPrompt:
    def test_contains_all_placeholders(self):
        expected = [
            "full_folder_path",
            "breadcrumb_path",
            "folder_name",
            "file_count",
            "file_summaries",
            "naming_rules",
            "custom_instructions",
        ]
        for placeholder in expected:
            assert f"{{{placeholder}}}" in HOLISTIC_NAMING_PROMPT, (
                f"Missing placeholder: {placeholder}"
            )

    def test_prompt_can_be_formatted(self):
        result = HOLISTIC_NAMING_PROMPT.format(
            full_folder_path="/tmp/docs",
            breadcrumb_path="docs > research",
            folder_name="research",
            file_count=5,
            file_summaries="File 1: ...\nFile 2: ...",
            naming_rules="- lowercase\n- hyphen-separated",
            custom_instructions="",
        )
        assert "research" in result


class TestApiLimits:
    def test_max_file_size(self):
        assert API_LIMITS["max_file_size_bytes"] == 2 * 1024**3

    def test_max_retries(self):
        assert API_LIMITS["max_retries"] == 5


class TestCostPerToken:
    def test_flash_model_costs(self):
        assert "gemini-2.0-flash" in COST_PER_TOKEN
        costs = COST_PER_TOKEN["gemini-2.0-flash"]
        assert "input" in costs
        assert "output" in costs
        assert costs["input"] > 0
        assert costs["output"] > 0

    def test_pro_costs_higher_than_flash(self):
        flash = COST_PER_TOKEN["gemini-2.0-flash"]
        pro = COST_PER_TOKEN["gemini-2.5-pro"]
        assert pro["input"] > flash["input"]
