"""
Configuration management for ai-file-rename.

Resolves configuration from multiple sources with this precedence:
1. CLI flags (highest)
2. Environment variables
3. Config file (~/.ai-rename.yaml)
4. Built-in defaults (lowest)
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Config(BaseModel):
    """Resolved configuration. Immutable after creation."""

    # Auth
    gemini_api_key: str = ""
    use_vertex_ai: bool = False
    vertex_project: Optional[str] = None
    vertex_location: Optional[str] = None

    # Model
    model: str = "gemini-2.5-flash"

    # Naming
    max_words: int = 8
    min_words: int = 2
    separator: str = "-"
    include_dates: bool = True
    language: str = "en"
    custom_instructions: Optional[str] = None

    # Safety
    max_files: int = 500
    cost_limit: float = 5.00
    require_confirmation: bool = True

    # Processing
    concurrency: int = 3
    convert_office_docs: bool = True
    skip_well_named: bool = True

    # Logging
    log_level: str = "INFO"
    log_dir: Path = Field(default_factory=lambda: Path.home() / ".ai-rename" / "logs")

    # Include / Exclude
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(
        default_factory=lambda: [".*", "*.tmp", "node_modules", "__pycache__", ".git"]
    )

    model_config = {"arbitrary_types_allowed": True}


# Environment variable prefix
_ENV_PREFIX = "AI_RENAME_"

# Map of config fields to their environment variable names (special cases)
_ENV_SPECIAL = {
    "gemini_api_key": "GEMINI_API_KEY",
}


def _load_yaml_config(config_path: Path) -> dict:
    """Load configuration from a YAML file."""
    if not config_path.exists():
        return {}

    try:
        import yaml
    except ImportError:
        return {}

    with open(config_path, "r") as f:
        data = yaml.safe_load(f) or {}

    # Flatten nested config structure
    flat = {}
    for key, value in data.items():
        if isinstance(value, dict):
            # Nested sections like 'naming:', 'safety:', etc.
            for sub_key, sub_value in value.items():
                flat[sub_key] = sub_value
        else:
            flat[key] = value

    return flat


def _get_env_value(field_name: str) -> Optional[str]:
    """Get a config value from environment variables."""
    # Check special mappings first
    if field_name in _ENV_SPECIAL:
        value = os.environ.get(_ENV_SPECIAL[field_name])
        if value is not None:
            return value

    # Check standard AI_RENAME_ prefix
    env_key = f"{_ENV_PREFIX}{field_name.upper()}"
    return os.environ.get(env_key)


def _coerce_value(value: str, field_name: str, config_cls: type) -> object:
    """Coerce a string environment variable to the expected type."""
    field_info = config_cls.model_fields.get(field_name)
    if field_info is None:
        return value

    annotation = field_info.annotation

    if annotation is bool or (hasattr(annotation, "__origin__") and annotation is bool):
        return value.lower() in ("true", "1", "yes")
    if annotation is int:
        return int(value)
    if annotation is float:
        return float(value)
    if annotation is Path:
        return Path(value).expanduser()

    return value


def load_config(
    config_path: Optional[Path] = None,
    cli_overrides: Optional[dict] = None,
) -> Config:
    """
    Load configuration with layered precedence.

    Args:
        config_path: Path to YAML config file. Defaults to ~/.ai-rename.yaml.
        cli_overrides: Dict of CLI flag values (only non-None values).

    Returns:
        Resolved Config object.
    """
    if cli_overrides is None:
        cli_overrides = {}

    # Layer 4: Built-in defaults (handled by Pydantic defaults)
    resolved = {}

    # Layer 3: Config file
    if config_path is None:
        config_path = Path.home() / ".ai-rename.yaml"
    yaml_values = _load_yaml_config(config_path)
    resolved.update(yaml_values)

    # Layer 2: Environment variables
    for field_name in Config.model_fields:
        env_value = _get_env_value(field_name)
        if env_value is not None:
            resolved[field_name] = _coerce_value(env_value, field_name, Config)

    # Layer 1: CLI flags (highest priority)
    for key, value in cli_overrides.items():
        if value is not None:
            resolved[key] = value

    # Ensure log_dir is expanded
    if "log_dir" in resolved and isinstance(resolved["log_dir"], str):
        resolved["log_dir"] = Path(resolved["log_dir"]).expanduser()

    return Config(**resolved)
