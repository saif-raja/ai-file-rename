"""
ai-file-rename: AI-powered file renaming using Google Gemini.

This package provides both a CLI tool and a Python library for
intelligently renaming files based on their content, metadata,
and folder context.

Usage as a library:
    from ai_file_rename import RenameSession

    session = RenameSession(target_dir="~/documents/", api_key="...")
    plan = session.analyze()
    result = session.execute(plan)
"""

__version__ = "1.0.0"

from ai_file_rename.config import Config, load_config
from ai_file_rename.models import (
    AnalyzedFile,
    ContentSummary,
    DiscoveryResult,
    ExecutionResult,
    FileCategory,
    FileEntry,
    FileMetadata,
    ImpactSummary,
    ProposedRename,
    RenameResult,
    ValidatedRename,
)
from ai_file_rename.session import RenamePlan, RenameSession, TokenUsage

__all__ = [
    # Core session API
    "RenameSession",
    "RenamePlan",
    "TokenUsage",
    # Configuration
    "Config",
    "load_config",
    # Data models
    "FileCategory",
    "FileEntry",
    "FileMetadata",
    "ContentSummary",
    "AnalyzedFile",
    "ProposedRename",
    "ValidatedRename",
    "RenameResult",
    "ExecutionResult",
    "ImpactSummary",
    "DiscoveryResult",
    # Meta
    "__version__",
]
