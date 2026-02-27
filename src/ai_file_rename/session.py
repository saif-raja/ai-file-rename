"""
Programmatic API for ai-file-rename.

RenameSession encapsulates the full pipeline in a clean Python API.
The CLI is a thin wrapper over this class.

Usage:
    from ai_file_rename import RenameSession

    session = RenameSession(
        target_dir="~/documents/research/",
        recursive=True,
        api_key="...",
    )
    plan = session.analyze()
    result = session.execute(plan)
    session.undo()
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ai_file_rename.config import Config, load_config
from ai_file_rename.logger import RenameLogger
from ai_file_rename.models import (
    DiscoveryResult,
    ExecutionResult,
    FileCategory,
    ValidatedRename,
)
from ai_file_rename.validator import is_well_named


def _generate_run_id() -> str:
    """Generate a unique run ID: {date}-{short-uuid}."""
    date_part = datetime.now().strftime("%Y%m%d")
    uuid_part = uuid.uuid4().hex[:8]
    return f"{date_part}-{uuid_part}"


@dataclass
class TokenUsage:
    """Accumulated token usage across API calls."""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, input_t: int, output_t: int) -> None:
        self.input_tokens += input_t
        self.output_tokens += output_t

    def merge(self, other) -> None:
        """Merge another TokenUsage or a dict with input_tokens/output_tokens."""
        if isinstance(other, dict):
            self.input_tokens += other.get("input_tokens", 0)
            self.output_tokens += other.get("output_tokens", 0)
        else:
            self.input_tokens += other.input_tokens
            self.output_tokens += other.output_tokens


@dataclass
class RenamePlan:
    """The result of the analysis phase — a plan of proposed renames.

    Contains everything needed to display a dry-run preview and execute.
    """
    discovery: DiscoveryResult
    validated_renames: list[ValidatedRename]
    skipped_well_named: list[str] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    run_id: str = ""
    target_directory: Path = Path(".")
    recursive: bool = False

    @property
    def total_renames(self) -> int:
        return len([v for v in self.validated_renames if not v.original.is_unchanged])

    @property
    def total_unchanged(self) -> int:
        return len([v for v in self.validated_renames if v.original.is_unchanged])

    @property
    def folders_affected(self) -> int:
        return self.discovery.impact.folders_affected


class RenameSession:
    """Encapsulates the full AI rename pipeline.

    Provides a clean programmatic API:
        plan = session.analyze()   # Discover, preprocess, analyze, name, validate
        result = session.execute(plan)  # Execute the renames
        session.undo()             # Reverse the last operation
    """

    def __init__(
        self,
        target_dir: str | Path,
        recursive: bool = False,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        config_path: Optional[str | Path] = None,
        custom_instructions: Optional[str] = None,
        max_files: Optional[int] = None,
        verbose: bool = False,
        **config_overrides,
    ):
        """Initialize a rename session.

        Args:
            target_dir: Directory to process.
            recursive: Whether to recurse into subdirectories.
            api_key: Gemini API key (or set GEMINI_API_KEY env var).
            model: Gemini model name (default: gemini-2.5-flash).
            config_path: Path to YAML config file.
            custom_instructions: Additional naming instructions.
            max_files: Safety limit on number of files.
            verbose: Enable verbose logging.
            **config_overrides: Additional config overrides.
        """
        self.target_dir = Path(target_dir).expanduser().resolve()
        self.recursive = recursive
        self.verbose = verbose

        # Build config overrides
        overrides = dict(config_overrides)
        if api_key is not None:
            overrides["gemini_api_key"] = api_key
        if model is not None:
            overrides["model"] = model
        if custom_instructions is not None:
            overrides["custom_instructions"] = custom_instructions
        if max_files is not None:
            overrides["max_files"] = max_files

        cfg_path = Path(config_path) if config_path else None
        self.config = load_config(config_path=cfg_path, cli_overrides=overrides)

        self.run_id = _generate_run_id()
        self.logger = RenameLogger(
            self.config.log_dir, self.run_id, verbose=verbose
        )

        # State
        self._last_plan: Optional[RenamePlan] = None
        self._client = None

    def _get_client(self):
        """Lazily initialize the Gemini client."""
        if self._client is None:
            from google import genai
            if self.config.use_vertex_ai:
                self._client = genai.Client(
                    vertexai=True,
                    project=self.config.vertex_project,
                    location=self.config.vertex_location,
                )
            else:
                self._client = genai.Client(api_key=self.config.gemini_api_key)
        return self._client

    def analyze(self) -> RenamePlan:
        """Run the full analysis pipeline: discover, preprocess, analyze, name, validate.

        Returns:
            A RenamePlan containing all proposed renames ready for review/execution.

        Raises:
            FileNotFoundError: If target directory doesn't exist.
            ValueError: If no API key is configured.
        """
        if not self.config.gemini_api_key:
            raise ValueError(
                "No API key found. Set GEMINI_API_KEY environment variable "
                "or pass api_key to RenameSession."
            )

        self.logger.info(f"Starting analysis session {self.run_id}")
        self.logger.info(f"Target: {self.target_dir}")

        # Phase 1: Discovery
        from ai_file_rename.discovery import discover

        discovery = discover(self.target_dir, self.recursive, self.config)

        if discovery.impact.supported_files == 0:
            self.logger.info("No supported files found.")
            plan = RenamePlan(
                discovery=discovery,
                validated_renames=[],
                run_id=self.run_id,
                target_directory=self.target_dir,
                recursive=self.recursive,
            )
            self._last_plan = plan
            return plan

        # Filter well-named files
        skipped_well_named = []
        processable_files = []
        for f in discovery.files:
            if f.category == FileCategory.UNSUPPORTED or f.skip_reason:
                continue
            if self.config.skip_well_named and is_well_named(f.name):
                skipped_well_named.append(f.name)
                self.logger.info(f"Skipping well-named: {f.name}")
                continue
            processable_files.append(f)

        if skipped_well_named:
            self.logger.info(
                f"Skipping {len(skipped_well_named)} already well-named files"
            )

        if not processable_files:
            self.logger.info("All files are already well-named.")
            plan = RenamePlan(
                discovery=discovery,
                validated_renames=[],
                skipped_well_named=skipped_well_named,
                run_id=self.run_id,
                target_directory=self.target_dir,
                recursive=self.recursive,
            )
            self._last_plan = plan
            return plan

        token_usage = TokenUsage()

        # Phase 2: Preprocessing
        from ai_file_rename.preprocessing import preprocess

        with tempfile.TemporaryDirectory(prefix="ai-rename-") as tmp:
            tmp_dir = Path(tmp)
            self.logger.info(f"Preprocessing {len(processable_files)} files...")
            enriched = preprocess(processable_files, tmp_dir, self.config)

            # Phase 3: Context building
            from ai_file_rename.context import build_context

            self.logger.info("Building folder context...")
            folder_contexts = build_context(enriched, self.target_dir)

            # Phase 4: Content analysis
            from ai_file_rename.analyzer import analyze_all

            client = self._get_client()
            self.logger.info("Analyzing file contents with Gemini...")

            analyzed, analysis_tokens = asyncio.run(
                analyze_all(
                    folder_contexts,
                    client,
                    self.config.model,
                    self.config,
                    concurrency=self.config.concurrency,
                )
            )
            token_usage.merge(analysis_tokens)

            # Phase 5: Holistic naming
            from ai_file_rename.namer import name_all

            self.logger.info("Generating holistic names...")
            proposed, naming_tokens = asyncio.run(
                name_all(
                    analyzed,
                    folder_contexts,
                    client,
                    self.config.model,
                    self.config,
                    concurrency=self.config.concurrency,
                )
            )
            token_usage.merge(naming_tokens)

        # Flatten all proposed renames
        all_renames = []
        for folder_path, renames_list in proposed.items():
            all_renames.extend(renames_list)

        if not all_renames:
            self.logger.info("No renames proposed.")
            plan = RenamePlan(
                discovery=discovery,
                validated_renames=[],
                skipped_well_named=skipped_well_named,
                token_usage=token_usage,
                run_id=self.run_id,
                target_directory=self.target_dir,
                recursive=self.recursive,
            )
            self._last_plan = plan
            return plan

        # Phase 6: Validation
        from ai_file_rename.validator import validate_renames

        self.logger.info(f"Validating {len(all_renames)} proposed renames...")
        existing_files = {f.name for f in discovery.files}
        files_being_renamed = {r.current_name for r in all_renames}

        validated = validate_renames(
            all_renames,
            symlink_map=discovery.symlink_map,
            existing_files=existing_files,
            files_being_renamed=files_being_renamed,
        )

        plan = RenamePlan(
            discovery=discovery,
            validated_renames=validated,
            skipped_well_named=skipped_well_named,
            token_usage=token_usage,
            run_id=self.run_id,
            target_directory=self.target_dir,
            recursive=self.recursive,
        )
        self._last_plan = plan

        self.logger.info(
            f"Analysis complete: {plan.total_renames} renames proposed, "
            f"{plan.total_unchanged} unchanged, "
            f"{len(skipped_well_named)} skipped (well-named)"
        )

        return plan

    def execute(self, plan: Optional[RenamePlan] = None) -> ExecutionResult:
        """Execute the renames from a plan.

        Args:
            plan: The RenamePlan to execute. If None, uses the last analyze() result.

        Returns:
            ExecutionResult with counts and individual results.

        Raises:
            ValueError: If no plan is available.
        """
        if plan is None:
            plan = self._last_plan
        if plan is None:
            raise ValueError("No plan available. Call analyze() first.")

        if not plan.validated_renames:
            self.logger.info("No renames to execute.")
            return ExecutionResult(
                run_id=plan.run_id,
                target_directory=plan.target_directory,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                total_files=0,
                renamed=0,
                skipped=0,
                failed=0,
                symlinks_updated=0,
                results=[],
                total_tokens_used=plan.token_usage.total_tokens,
                estimated_cost_usd=self._estimate_cost(plan.token_usage),
            )

        from ai_file_rename.executor import execute_renames

        self.logger.info(f"Executing {len(plan.validated_renames)} renames...")
        result = execute_renames(
            plan.validated_renames,
            manifest_dir=plan.target_directory,
            run_id=plan.run_id,
            config=self.config,
            symlink_map=plan.discovery.symlink_map,
        )

        # Attach token usage
        result.total_tokens_used = plan.token_usage.total_tokens
        result.estimated_cost_usd = self._estimate_cost(plan.token_usage)

        # Write to history
        self._record_history(result, plan)

        # Write to CSV ledger
        self._record_csv_ledger(result, plan)

        self.logger.info(
            f"Execution complete: {result.renamed} renamed, "
            f"{result.skipped} skipped, {result.failed} failed"
        )

        return result

    def undo(self) -> ExecutionResult:
        """Undo the last rename operation in the target directory.

        Returns:
            ExecutionResult describing the undo operation.

        Raises:
            FileNotFoundError: If no manifest exists.
        """
        from ai_file_rename.executor import undo_renames

        self.logger.info(f"Undoing renames in {self.target_dir}")
        result = undo_renames(self.target_dir)
        self.logger.info(
            f"Undo complete: {result.renamed} restored, {result.failed} failed"
        )
        return result

    def _estimate_cost(self, usage: TokenUsage) -> float:
        """Estimate cost from token usage."""
        from ai_file_rename.constants import COST_PER_TOKEN

        costs = COST_PER_TOKEN.get(self.config.model, {})
        input_cost = costs.get("input", 0.0)
        output_cost = costs.get("output", 0.0)

        return round(
            (usage.input_tokens * input_cost)
            + (usage.output_tokens * output_cost),
            4,
        )

    def _record_history(self, result: ExecutionResult, plan: RenamePlan) -> None:
        """Write to the global JSONL history log."""
        record = {
            "run_id": plan.run_id,
            "run_started_at": result.started_at.isoformat(),
            "run_completed_at": (
                result.completed_at.isoformat() if result.completed_at else None
            ),
            "target_directory": str(plan.target_directory),
            "recursive": plan.recursive,
            "model_used": self.config.model,
            "files_discovered": plan.discovery.impact.total_files,
            "folders_touched": plan.discovery.impact.folders_affected,
            "files_renamed": result.renamed,
            "files_skipped": result.skipped,
            "files_failed": result.failed,
            "files_well_named_skipped": len(plan.skipped_well_named),
            "symlinks_updated": result.symlinks_updated,
            "total_tokens": plan.token_usage.total_tokens,
            "input_tokens": plan.token_usage.input_tokens,
            "output_tokens": plan.token_usage.output_tokens,
            "estimated_cost_usd": result.estimated_cost_usd,
            "renames": [
                {"old": r.old_path.name, "new": r.new_path.name}
                for r in result.results
                if r.status == "completed"
            ],
        }
        self.logger.append_to_history(record)

    def _record_csv_ledger(self, result: ExecutionResult, plan: RenamePlan) -> None:
        """Append a row to the CSV session ledger."""
        duration = 0.0
        if result.completed_at and result.started_at:
            duration = (result.completed_at - result.started_at).total_seconds()

        self.logger.append_to_csv_ledger({
            "timestamp": (result.completed_at or result.started_at).isoformat(),
            "run_id": plan.run_id,
            "target_directory": str(plan.target_directory),
            "recursive": str(plan.recursive),
            "total_files_discovered": plan.discovery.impact.total_files,
            "total_folders_touched": plan.discovery.impact.folders_affected,
            "files_renamed": result.renamed,
            "files_skipped": result.skipped,
            "files_failed": result.failed,
            "symlinks_updated": result.symlinks_updated,
            "model_used": self.config.model,
            "estimated_tokens": plan.token_usage.total_tokens,
            "estimated_cost_usd": result.estimated_cost_usd,
            "duration_seconds": round(duration, 1),
        })
