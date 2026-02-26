"""Tests for ai_file_rename.config — configuration loading and resolution."""

import os
import tempfile
from pathlib import Path

import pytest

from ai_file_rename.config import Config, load_config


class TestConfigDefaults:
    def test_default_model(self):
        config = Config(gemini_api_key="test")
        assert config.model == "gemini-2.5-flash"

    def test_default_max_files(self):
        config = Config(gemini_api_key="test")
        assert config.max_files == 500

    def test_default_separator(self):
        config = Config(gemini_api_key="test")
        assert config.separator == "-"

    def test_default_cost_limit(self):
        config = Config(gemini_api_key="test")
        assert config.cost_limit == 5.00

    def test_default_concurrency(self):
        config = Config(gemini_api_key="test")
        assert config.concurrency == 3

    def test_default_exclude_patterns(self):
        config = Config(gemini_api_key="test")
        assert ".*" in config.exclude_patterns
        assert ".git" in config.exclude_patterns

    def test_default_log_dir(self):
        config = Config(gemini_api_key="test")
        assert "ai-rename" in str(config.log_dir)


class TestConfigOverrides:
    def test_cli_override_model(self):
        config = load_config(
            config_path=Path("/nonexistent"),
            cli_overrides={"model": "gemini-2.5-pro", "gemini_api_key": "test"},
        )
        assert config.model == "gemini-2.5-pro"

    def test_cli_override_max_files(self):
        config = load_config(
            config_path=Path("/nonexistent"),
            cli_overrides={"max_files": 1000, "gemini_api_key": "test"},
        )
        assert config.max_files == 1000


class TestConfigFromYaml:
    def test_load_yaml_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("gemini_api_key: yaml-key\n")
            f.write("model: gemini-2.5-flash\n")
            f.write("naming:\n")
            f.write("  max_words: 10\n")
            f.write("  separator: _\n")
            f.flush()
            config_path = Path(f.name)

        try:
            config = load_config(config_path=config_path)
            assert config.gemini_api_key == "yaml-key"
            assert config.model == "gemini-2.5-flash"
            assert config.max_words == 10
            assert config.separator == "_"
        finally:
            os.unlink(config_path)

    def test_missing_yaml_file_uses_defaults(self):
        config = load_config(
            config_path=Path("/nonexistent/config.yaml"),
            cli_overrides={"gemini_api_key": "test"},
        )
        assert config.model == "gemini-2.5-flash"


class TestConfigFromEnv:
    def test_gemini_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")
        config = load_config(config_path=Path("/nonexistent"))
        assert config.gemini_api_key == "env-key"

    def test_model_from_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setenv("AI_RENAME_MODEL", "gemini-2.5-pro")
        config = load_config(config_path=Path("/nonexistent"))
        assert config.model == "gemini-2.5-pro"

    def test_cli_overrides_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")
        monkeypatch.setenv("AI_RENAME_MODEL", "gemini-2.5-flash")
        config = load_config(
            config_path=Path("/nonexistent"),
            cli_overrides={"model": "gemini-2.5-pro"},
        )
        # CLI should win over env
        assert config.model == "gemini-2.5-pro"
        assert config.gemini_api_key == "env-key"


class TestConfigPrecedence:
    def test_cli_beats_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("gemini_api_key: yaml-key\n")
            f.write("model: gemini-2.5-flash\n")
            f.flush()
            config_path = Path(f.name)

        try:
            config = load_config(
                config_path=config_path,
                cli_overrides={"model": "gemini-2.5-pro"},
            )
            assert config.model == "gemini-2.5-pro"
            assert config.gemini_api_key == "yaml-key"
        finally:
            os.unlink(config_path)
