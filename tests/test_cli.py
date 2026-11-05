"""Tests for ai_file_rename.cli: CLI entrypoint and command wiring."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_file_rename.cli import main


FIXTURES = Path(__file__).parent / "fixtures" / "sample-files"


class TestCliBasics:
    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output

    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "rename" in result.output
        assert "undo" in result.output
        assert "history" in result.output

    def test_rename_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["rename", "--help"])
        assert result.exit_code == 0
        assert "--recursive" in result.output
        assert "--execute" in result.output
        assert "--headless" in result.output
        assert "--model" in result.output

    def test_undo_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["undo", "--help"])
        assert result.exit_code == 0

    def test_history_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["history", "--help"])
        assert result.exit_code == 0
        assert "--directory" in result.output
        assert "--last" in result.output
        assert "--json" in result.output


class TestRenameCommand:
    def test_rename_no_api_key(self):
        """Test that rename fails without API key."""
        runner = CliRunner()
        result = runner.invoke(main, ["rename", str(FIXTURES / "text")])
        assert result.exit_code != 0
        assert "API key" in result.output or "api" in result.output.lower()

    def test_rename_vertex_ai_skips_api_key_check(self, tmp_path, monkeypatch):
        """When use_vertex_ai is True, missing API key should not cause exit."""
        # Create a config file that sets use_vertex_ai
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "use_vertex_ai: true\nvertex_project: my-project\nvertex_location: us-central1\n"
        )
        # Remove the API key env var to ensure it's not set
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        runner = CliRunner()
        result = runner.invoke(main, [
            "rename", str(FIXTURES / "text"),
            "--config", str(config_file),
            "--headless",
        ])
        # It should NOT fail with "No API key found"
        assert "No API key found" not in (result.output or "")

    def test_rename_nonexistent_dir(self):
        """Test that rename fails with nonexistent directory."""
        runner = CliRunner()
        result = runner.invoke(main, ["rename", "/nonexistent/path"])
        assert result.exit_code != 0


class TestHistoryCommand:
    def test_history_empty(self, temp_dir):
        """Test history with no prior runs."""
        runner = CliRunner()
        result = runner.invoke(main, ["history"])
        assert result.exit_code == 0
        # Should handle empty history gracefully

    def test_history_json_format(self, temp_dir):
        """Test history JSON output."""
        runner = CliRunner()
        result = runner.invoke(main, ["history", "--json"])
        assert result.exit_code == 0


class TestUndoCommand:
    def test_undo_no_manifest_with_force(self, temp_dir):
        """Test undo with --force when no manifest exists raises error."""
        runner = CliRunner()
        result = runner.invoke(main, ["undo", str(temp_dir), "--force"])
        # Should fail because no manifest exists
        assert result.exit_code != 0
        assert "No manifest" in result.output or "Error" in result.output

    def test_undo_no_input_aborts(self, temp_dir):
        """Test undo without --force aborts when user declines prompt."""
        runner = CliRunner()
        result = runner.invoke(main, ["undo", str(temp_dir)], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output
