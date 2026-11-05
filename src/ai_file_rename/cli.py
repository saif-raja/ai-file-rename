"""
CLI entrypoint for ai-file-rename.

Thin wrapper over RenameSession: handles interactive prompts, Rich display,
and run reports. Does NOT contain business logic.
"""

import contextlib
import sys
from datetime import datetime
from pathlib import Path

import click

from ai_file_rename import __version__
from ai_file_rename.config import load_config
from ai_file_rename.logger import RenameLogger
from ai_file_rename.session import RenameSession, generate_run_id


# ---------------------------------------------------------------------------
# Rich progress helpers
# ---------------------------------------------------------------------------

def _get_console(plain: bool = False):
    """Return a Rich Console, or None if Rich is unavailable or --plain is set."""
    if plain:
        return None
    try:
        from rich.console import Console
        return Console()
    except ImportError:
        return None


@contextlib.contextmanager
def _phase_status(console, message: str):
    """Context manager that shows a Rich spinner during a pipeline phase.

    If Rich is not available (console is None), falls back to structured
    plain-text output suitable for agent consumption.
    On success the spinner is replaced with a green checkmark line.
    """
    if console is not None:
        try:
            with console.status(
                f"[bold cyan]{message}...[/bold cyan]", spinner="dots"
            ):
                yield
            console.print(f"[green]\u2713[/green] {message}")
            return
        except Exception:
            pass
    # Plain text fallback: structured for agent parsing
    print(f"[PHASE] {message} ...")
    yield
    print(f"[DONE]  {message}")


class RunReport:
    """Stateful run report that is rewritten at each pipeline phase.

    The same timestamped file is updated progressively as phases complete,
    so anyone watching the target directory can see current pipeline status.
    The final state of this file IS the complete run report.
    """

    def __init__(self, target: Path, run_id: str, config):
        self.target = target
        self.run_id = run_id
        self.config = config
        self.timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.report_path = target / f".ai-rename-report-{run_id}.md"

        # Accumulated data (set progressively)
        self.status = "initializing"
        self.recursive = False
        self.discovery = None
        self.analyzed_count = 0
        self.analysis_failures: list = []   # list of (name, reason)
        self.validated: list = []
        self.total_tokens: dict = {}
        self.executed = False
        self.result = None

    def update(self, status: str, **kwargs) -> None:
        """Update the report status and any new data, then rewrite the file."""
        self.status = status
        for key, value in kwargs.items():
            setattr(self, key, value)
        try:
            self._write()
        except OSError:
            pass  # Non-fatal: don't crash the pipeline for a report write

    def _write(self) -> None:
        from ai_file_rename.constants import COST_PER_TOKEN

        model_costs = COST_PER_TOKEN.get(self.config.model, {})
        est_cost = (
            self.total_tokens.get("input_tokens", 0) * model_costs.get("input", 0)
            + self.total_tokens.get("output_tokens", 0) * model_costs.get("output", 0)
        )

        mode = "executed" if self.executed else "dry-run"

        lines = [
            "# ai-rename report",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| Run ID | `{self.run_id}` |",
            f"| Started | {self.timestamp} |",
            f"| Status | **{self.status}** |",
            f"| Mode | **{mode}** |",
            f"| Target | `{self.target}` |",
            f"| Recursive | {'yes' if self.recursive else 'no'} |",
            f"| Model | {self.config.model} |",
        ]

        # Impact section (available after discovery)
        if self.discovery:
            imp = self.discovery.impact
            lines.extend([
                "",
                "## Impact",
                "",
                f"- Files discovered: {imp.total_files} "
                f"({imp.supported_files} supported, "
                f"{imp.unsupported_files} unsupported)",
            ])
            if self.analyzed_count:
                lines.append(
                    f"- Files analyzed: {self.analyzed_count}"
                )
            if self.analysis_failures:
                lines.append(
                    f"- Analysis failures: {len(self.analysis_failures)}"
                )
            if self.validated:
                rename_count = sum(
                    1 for v in self.validated if not v.original.is_unchanged
                )
                unchanged_count = sum(
                    1 for v in self.validated if v.original.is_unchanged
                )
                lines.append(
                    f"- Names proposed: {len(self.validated)} "
                    f"({rename_count} renames, {unchanged_count} unchanged)"
                )
            if self.total_tokens:
                lines.append(
                    f"- Tokens: "
                    f"{self.total_tokens.get('input_tokens', 0):,} input + "
                    f"{self.total_tokens.get('output_tokens', 0):,} output"
                )
                lines.append(f"- Estimated cost: ${est_cost:.4f}")

            if self.result:
                lines.extend([
                    "",
                    f"- Files renamed: {self.result.renamed}",
                    f"- Files skipped: {self.result.skipped}",
                    f"- Files failed: {self.result.failed}",
                    f"- Symlinks updated: {self.result.symlinks_updated}",
                ])

        # Rename table (available after validation)
        if self.validated:
            lines.extend([
                "",
                "## Proposed Renames",
                "",
                "| # | Current Name | Proposed Name | Notes |",
                "|---|-------------|---------------|-------|",
            ])
            for i, v in enumerate(self.validated, 1):
                notes = ""
                if v.original.is_unchanged:
                    notes = "unchanged"
                elif v.validation_notes:
                    notes = "; ".join(v.validation_notes)
                lines.append(
                    f"| {i} | {v.original.current_name} "
                    f"| {v.final_name} | {notes} |"
                )

        # Analysis failures
        if self.analysis_failures:
            lines.extend([
                "",
                f"## Analysis Failures: {len(self.analysis_failures)} files",
                "",
            ])
            for name, reason in self.analysis_failures:
                lines.append(f"- **{name}**: {reason}")

        lines.append("")
        self.report_path.write_text("\n".join(lines), encoding="utf-8")


def _display_impact_summary(impact, use_rich: bool = True) -> None:
    """Display the impact assessment to the user."""
    if use_rich:
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.table import Table

            console = Console()

            # Build the summary text
            lines = [
                f"Target:           {impact.target_directory}",
                f"Mode:             {'Recursive' if impact.recursive else 'Single folder'}",
                "",
                f"Files found:      {impact.total_files}",
                f"  Supported:      {impact.supported_files} (will be processed)",
                f"  Unsupported:    {impact.unsupported_files} (will be skipped)",
                "",
                f"Folders affected: {impact.folders_affected}",
                f"Deepest nesting:  {impact.deepest_nesting} levels",
                "",
                f"Est. API calls:   ~{impact.estimated_api_calls}",
                f"Est. cost:        ~${impact.estimated_cost_usd:.2f}",
            ]

            console.print(Panel(
                "\n".join(lines),
                title="IMPACT ASSESSMENT",
                border_style="cyan",
            ))

            # File type breakdown
            if impact.file_type_breakdown:
                table = Table(title="File Types")
                table.add_column("Extension", style="cyan")
                table.add_column("Count", justify="right")
                table.add_column("Percentage", justify="right")

                total = sum(impact.file_type_breakdown.values())
                for ext, count in sorted(
                    impact.file_type_breakdown.items(),
                    key=lambda x: x[1],
                    reverse=True,
                ):
                    pct = (count / total * 100) if total > 0 else 0
                    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                    table.add_row(ext, str(count), f"{bar} {pct:.0f}%")

                console.print(table)

            # Warnings
            for warning in impact.warnings:
                console.print(f"[yellow]⚠ {warning}[/yellow]")

            return
        except ImportError:
            pass

    # Plain text: structured key: value format for agent parsing
    print(f"\n[IMPACT ASSESSMENT]")
    print(f"target_directory: {impact.target_directory}")
    print(f"mode: {'recursive' if impact.recursive else 'single_folder'}")
    print(f"total_files: {impact.total_files}")
    print(f"supported_files: {impact.supported_files}")
    print(f"unsupported_files: {impact.unsupported_files}")
    print(f"folders_affected: {impact.folders_affected}")
    print(f"deepest_nesting: {impact.deepest_nesting}")
    print(f"symlinks_found: {impact.symlinks_found}")
    print(f"estimated_api_calls: {impact.estimated_api_calls}")
    print(f"estimated_cost_usd: {impact.estimated_cost_usd:.2f}")
    if impact.file_type_breakdown:
        print(f"file_types: {dict(sorted(impact.file_type_breakdown.items(), key=lambda x: -x[1]))}")
    for w in impact.warnings:
        print(f"WARNING: {w}")
    print()


def _display_dry_run(renames, use_rich: bool = True) -> None:
    """Display the proposed renames table."""
    rich_available = False
    if use_rich:
        try:
            from rich.console import Console
            from rich.table import Table

            rich_available = True
            console = Console()
            table = Table(title="PROPOSED RENAMES")
            table.add_column("#", justify="right", style="dim")
            table.add_column("Current Name", style="red")
            table.add_column("Proposed Name", style="green")
            table.add_column("Notes", style="yellow")

            for i, rename in enumerate(renames, 1):
                notes = ""
                if rename.validation_notes:
                    notes = "; ".join(rename.validation_notes)
                elif rename.original.is_unchanged:
                    notes = "unchanged"

                table.add_row(
                    str(i),
                    rename.original.current_name,
                    rename.final_name,
                    notes,
                )

            console.print(table)
        except ImportError:
            pass

    if not rich_available:
        # Plain text: one line per rename, pipe-delimited for easy parsing
        print(f"\n[PROPOSED RENAMES] count={len(renames)}")
        for i, rename in enumerate(renames, 1):
            notes = ""
            if rename.validation_notes:
                notes = "; ".join(rename.validation_notes)
            elif rename.original.is_unchanged:
                notes = "unchanged"
            status = "unchanged" if rename.original.is_unchanged else "rename"
            print(
                f"  {i:3d}. [{status}] "
                f"{rename.original.current_name} -> {rename.final_name}"
                f"{f'  ({notes})' if notes and status != 'unchanged' else ''}"
            )
        print()



def _interactive_review(
    validated: list,
) -> tuple[list, bool]:
    """
    Interactive dry-run review with Approve/Reject/Edit/Save options.

    Returns:
        Tuple of (possibly-modified validated list, should_execute bool).
    """
    click.echo("\n" + "─" * 60)
    click.echo(" [A] Approve all   : execute all proposed renames")
    click.echo(" [R] Reject all    : abort, no changes")
    click.echo(" [E] Edit          : review each file individually")
    click.echo(" [S] Save & quit   : save plan to JSON for later")
    click.echo("─" * 60)

    choice = click.prompt(
        "Action",
        type=click.Choice(["a", "r", "e", "s"], case_sensitive=False),
        default="r",
    ).lower()

    if choice == "a":
        return validated, True

    if choice == "r":
        return validated, False

    if choice == "s":
        import json
        save_path = Path("ai-rename-plan.json")
        plan_data = []
        for v in validated:
            plan_data.append({
                "current_name": v.original.current_name,
                "proposed_name": v.final_name,
                "reasoning": v.original.reasoning,
                "confidence": v.original.confidence,
            })
        save_path.write_text(json.dumps(plan_data, indent=2))
        click.echo(f"Plan saved to {save_path.resolve()}")
        return validated, False

    if choice == "e":
        return _edit_individually(validated)

    return validated, False


def _edit_individually(validated: list) -> tuple[list, bool]:
    """Let the user review each rename: accept, reject, or retype."""
    from ai_file_rename.validator import sanitize_name

    kept = []

    for i, v in enumerate(validated, 1):
        current = v.original.current_name
        proposed = v.final_name

        if v.original.is_unchanged:
            click.echo(f"  [{i}/{len(validated)}] {current}: unchanged, skipping")
            kept.append(v)
            continue

        click.echo(f"\n  [{i}/{len(validated)}] {current}")
        click.echo(f"         -> {proposed}")
        click.echo(f"         ({v.original.reasoning})")

        action = click.prompt(
            "    [a]ccept / [r]eject / [c]ustom name",
            type=click.Choice(["a", "r", "c"], case_sensitive=False),
            default="a",
        ).lower()

        if action == "a":
            kept.append(v)
        elif action == "r":
            click.echo(f"    Skipped: {current}")
            continue
        elif action == "c":
            custom = click.prompt("    Enter new name (without extension)")
            ext = Path(current).suffix
            clean = sanitize_name(custom)
            final = f"{clean}{ext}"
            click.echo(f"    Using: {final}")

            # Create modified ValidatedRename
            from ai_file_rename.models import ProposedRename, ValidatedRename as VR

            new_rename = VR(
                original=ProposedRename(
                    current_name=v.original.current_name,
                    proposed_name=final,
                    current_path=v.original.current_path,
                    proposed_path=v.original.current_path.parent / final,
                    reasoning=f"User-specified: {custom}",
                    confidence=1.0,
                    is_unchanged=False,
                    has_incoming_symlinks=v.original.has_incoming_symlinks,
                    incoming_symlinks=v.original.incoming_symlinks,
                ),
                final_name=final,
                validation_notes=["User-edited name"],
            )
            kept.append(new_rename)

    if not kept:
        click.echo("\nAll renames rejected.")
        return kept, False

    click.echo(f"\n{len(kept)} renames approved. Execute? ", nl=False)
    if click.confirm("", default=True):
        return kept, True

    return kept, False


def _display_execution_result(result, use_rich: bool = True) -> None:
    """Display the execution summary."""
    duration = 0
    if result.completed_at and result.started_at:
        duration = (result.completed_at - result.started_at).total_seconds()

    if use_rich:
        try:
            from rich.console import Console
            from rich.panel import Panel

            console = Console()
            lines = [
                f"Files processed:  {result.total_files}",
                f"Files renamed:    {result.renamed}",
                f"Files skipped:    {result.skipped}",
                f"Files failed:     {result.failed}",
                f"Symlinks updated: {result.symlinks_updated}",
                f"Duration:         {duration:.1f}s",
            ]

            if result.total_tokens_used:
                lines.append(f"Tokens used:      {result.total_tokens_used:,}")
            if result.estimated_cost_usd:
                lines.append(f"Estimated cost:   ${result.estimated_cost_usd:.2f}")

            style = "green" if result.failed == 0 else "red"
            console.print(Panel(
                "\n".join(lines),
                title="EXECUTION SUMMARY",
                border_style=style,
            ))

            for warning in getattr(result, "warnings", []):
                console.print(f"[yellow]Warning: {warning}[/yellow]")

            return
        except ImportError:
            pass

    # Plain text: structured for agent parsing
    print(f"\n[EXECUTION SUMMARY]")
    print(f"total_files: {result.total_files}")
    print(f"files_renamed: {result.renamed}")
    print(f"files_skipped: {result.skipped}")
    print(f"files_failed: {result.failed}")
    print(f"symlinks_updated: {result.symlinks_updated}")
    print(f"duration_seconds: {duration:.1f}")
    if result.total_tokens_used:
        print(f"tokens_used: {result.total_tokens_used}")
    if result.estimated_cost_usd:
        print(f"estimated_cost_usd: {result.estimated_cost_usd:.4f}")
    print(f"status: {'success' if result.failed == 0 else 'partial_failure'}")
    for warning in getattr(result, "warnings", []):
        print(f"WARNING: {warning}")


# --- CLI Commands ---


@click.group()
@click.version_option(version=__version__)
def main():
    """AI-powered file renaming tool using Google Gemini."""
    pass


@main.command()
@click.argument("target_directory", type=click.Path(exists=True))
@click.option("--recursive", "-r", is_flag=True, help="Process subdirectories recursively")
@click.option("--execute", "-x", is_flag=True, help="Execute renames (skip dry-run)")
@click.option("--headless", "-H", is_flag=True, help="No interactive prompts")
@click.option("--config", "-c", "config_path", type=click.Path(), default=None)
@click.option("--model", "-m", default=None, help="Gemini model to use")
@click.option("--max-files", default=None, type=int)
@click.option("--custom-instructions", "-i", default=None)
@click.option("--verbose", "-v", is_flag=True)
@click.option("--cost-limit", default=None, type=float)
@click.option("--dry-run", "-d", is_flag=True, default=False, help="Explicit dry-run mode (default behavior)")
@click.option("--include", default=None, type=str, help="Glob pattern for files to include")
@click.option("--exclude", default=None, type=str, help="Glob pattern for files to exclude")
@click.option("--skip-converted", is_flag=True, default=False, help="Skip format conversion")
@click.option(
    "--log-level", default=None,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Set log level",
)
@click.option("--plain", "-P", is_flag=True, default=False,
              help="Plain text output (no Rich formatting). Best for agent/script consumption.")
def rename(target_directory, recursive, execute, headless, config_path, model,
           max_files, custom_instructions, verbose, cost_limit,
           dry_run, include, exclude, skip_converted, log_level, plain):
    """Rename files using AI-powered content analysis."""
    # --dry-run explicitly disables execute mode
    if dry_run:
        execute = False

    # --plain or --headless both disable Rich rendering
    use_rich = not plain and not headless
    console = _get_console(plain=not use_rich)

    # Build config overrides for non-named Session params
    config_overrides = {}
    if cost_limit is not None:
        config_overrides["cost_limit"] = cost_limit
    if headless:
        config_overrides["require_confirmation"] = False
    if include is not None:
        config_overrides["include_patterns"] = [include]
    if exclude is not None:
        config_overrides["exclude_patterns"] = [exclude]
    if skip_converted:
        config_overrides["convert_office_docs"] = False
    if log_level is not None:
        config_overrides["log_level"] = log_level.upper()

    # Create RenameSession: handles config, client, run ID, logger
    session = RenameSession(
        target_dir=target_directory,
        recursive=recursive,
        config_path=config_path,
        model=model,
        max_files=max_files,
        custom_instructions=custom_instructions,
        verbose=verbose,
        **config_overrides,
    )

    config = session.config
    target = session.target_dir
    run_id = session.run_id
    logger = session.logger

    if not config.gemini_api_key and not config.use_vertex_ai:
        click.echo(
            "Error: No API key found. Set GEMINI_API_KEY environment variable "
            "or add it to ~/.ai-rename.yaml",
            err=True,
        )
        sys.exit(1)

    # Create the stateful run report: rewritten at each phase transition
    report = RunReport(target, run_id, config)
    report.recursive = recursive
    report.update("starting")

    logger.info(f"Starting rename session {run_id}")
    logger.info(f"Target: {target}")
    logger.info(f"Model: {config.model}")

    # Check for existing manifest (interrupted previous run)
    from ai_file_rename.manifest import Manifest
    existing = Manifest.load_existing(target)
    if existing and existing.is_interrupted:
        click.echo("⚠ A previous rename operation was interrupted in this directory.")
        click.echo(f"  Completed: {len(existing.completed_renames)}")
        click.echo(f"  Pending:   {len(existing.pending_renames)}")
        if not headless:
            choice = click.prompt(
                "Choose action",
                type=click.Choice(["resume", "undo", "discard"]),
                default="discard",
            )
            if choice == "undo":
                from ai_file_rename.executor import undo_renames
                result = undo_renames(target)
                _display_execution_result(result, use_rich=use_rich)
                return
            elif choice == "resume":
                from ai_file_rename.executor import execute_renames
                from ai_file_rename.models import ProposedRename, ValidatedRename

                pending = existing.pending_renames
                if not pending:
                    click.echo("No pending renames to resume.")
                    existing.cleanup()
                    return

                # Reconstruct ValidatedRename objects from manifest entries
                resumed_renames = []
                for entry in pending:
                    old_path = Path(entry["old_path"])
                    new_path = Path(entry["new_path"])
                    proposed = ProposedRename(
                        current_name=entry["old_name"],
                        proposed_name=entry["new_name"],
                        current_path=old_path,
                        proposed_path=new_path,
                        reasoning="Resumed from interrupted session",
                        confidence=1.0,
                        is_unchanged=False,
                    )
                    validated_entry = ValidatedRename(
                        original=proposed,
                        final_name=entry["new_name"],
                        validation_notes=["Resumed from manifest"],
                    )
                    resumed_renames.append(validated_entry)

                click.echo(f"Resuming {len(resumed_renames)} pending renames...")
                logger.info(
                    f"Resuming {len(resumed_renames)} renames from "
                    f"interrupted session {existing.run_id}"
                )

                # Clean up the old manifest before executing (execute_renames
                # will create a fresh one for the resumed batch)
                existing.cleanup()

                result = execute_renames(
                    resumed_renames,
                    manifest_dir=target,
                    run_id=run_id,
                    config=config,
                )
                _display_execution_result(result, use_rich=use_rich)

                # Record resumed session in history and CSV ledger.
                # Schema matches Session._record_history() / _record_csv_ledger()
                # with zero tokens/cost (no API calls for resume).
                # Note: recursive is unknown from manifest data, so it defaults to False.
                logger.append_to_history({
                    "run_id": run_id,
                    "run_started_at": result.started_at.isoformat(),
                    "run_completed_at": (
                        result.completed_at.isoformat()
                        if result.completed_at else None
                    ),
                    "target_directory": str(target),
                    "recursive": False,
                    "model_used": config.model,
                    "files_discovered": 0,
                    "folders_touched": 0,
                    "files_renamed": result.renamed,
                    "files_skipped": result.skipped,
                    "files_failed": result.failed,
                    "symlinks_updated": result.symlinks_updated,
                    "total_tokens": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "resumed_from": existing.run_id,
                    "renames": [
                        {"old": r.old_path.name, "new": r.new_path.name}
                        for r in result.results
                        if r.status == "completed"
                    ],
                })

                duration = 0.0
                if result.completed_at and result.started_at:
                    duration = (
                        result.completed_at - result.started_at
                    ).total_seconds()
                logger.append_to_csv_ledger({
                    "timestamp": (
                        result.completed_at or result.started_at
                    ).isoformat(),
                    "run_id": run_id,
                    "target_directory": str(target),
                    "recursive": "False",
                    "total_files_discovered": 0,
                    "total_folders_touched": 0,
                    "files_renamed": result.renamed,
                    "files_skipped": result.skipped,
                    "files_failed": result.failed,
                    "symlinks_updated": result.symlinks_updated,
                    "model_used": config.model,
                    "estimated_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "duration_seconds": round(duration, 1),
                })

                logger.info(f"Resume session {run_id} complete.")
                return
            elif choice == "discard":
                existing.cleanup()
        else:
            existing.cleanup()

    # Phase 1: Discovery (via Session)
    try:
        with _phase_status(console, "Discovering files"):
            discovery = session.discover()
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    _display_impact_summary(discovery.impact, use_rich=use_rich)
    report.update("discovered", discovery=discovery)

    if discovery.impact.supported_files == 0:
        click.echo("No supported files found. Nothing to do.")
        return

    # Confirm before proceeding
    if config.require_confirmation and not headless:
        if not click.confirm("Proceed with content analysis?", default=True):
            click.echo("Aborted.")
            return

    # Cost check
    if discovery.impact.estimated_cost_usd > config.cost_limit:
        click.echo(
            f"⚠ Estimated cost ${discovery.impact.estimated_cost_usd:.2f} "
            f"exceeds limit ${config.cost_limit:.2f}"
        )
        if not headless:
            if not click.confirm("Continue anyway?", default=False):
                click.echo("Aborted.")
                return

    # Phases 2-6: Preprocess, analyze, name, validate (via Session)
    report.update("analyzing", analyzed_count=discovery.impact.supported_files)

    # Phase progress callback: drives Rich spinner + plain text output
    _phase_messages = {
        "preprocessing": "Preprocessing {file_count} files",
        "context": "Building folder context",
        "analyzing": "Analyzing file contents with Gemini",
        "naming": "Generating holistic names",
        "validating": "Validating {rename_count} proposed renames",
    }

    def _print_done(msg):
        """Print a phase-completion line (checkmark or plain text)."""
        if console is not None:
            try:
                console.print(f"[green]\u2713[/green] {msg}")
                return
            except Exception:
                pass
        print(f"[DONE]  {msg}")

    def _print_start(msg):
        """Print a phase-start line (plain text, used when no spinner)."""
        if console is not None:
            try:
                console.print(f"[bold cyan]\u22ef[/bold cyan] {msg}...")
                return
            except Exception:
                pass
        print(f"[PHASE] {msg} ...")

    prev_phase = None
    status_obj = None

    def _on_phase(phase, **kwargs):
        nonlocal prev_phase
        msg = _phase_messages.get(phase, phase)
        try:
            msg = msg.format(**kwargs)
        except KeyError:
            pass

        # Complete previous phase
        if prev_phase is not None:
            _print_done(prev_phase)

        # Start new phase: update spinner if available, else print static line
        if status_obj is not None:
            try:
                status_obj.update(f"[bold cyan]{msg}...[/bold cyan]")
            except Exception:
                _print_start(msg)
        else:
            _print_start(msg)

        prev_phase = msg

    try:
        # Start animated spinner (Rich) or nothing (plain text)
        if console is not None:
            try:
                status_obj = console.status(
                    "[bold cyan]Initializing...[/bold cyan]", spinner="dots"
                )
                status_obj.start()
            except Exception:
                status_obj = None

        plan = session.analyze(discovery=discovery, on_phase=_on_phase)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        if status_obj is not None:
            try:
                status_obj.stop()
            except Exception:
                pass

    # Complete the last phase
    if prev_phase is not None:
        _print_done(prev_phase)

    # Display analysis failures from plan
    if plan.analysis_failures:
        if use_rich:
            try:
                from rich.console import Console as _C
                _c = _C()
                _c.print(
                    f"\n[yellow]Analysis failed for "
                    f"{len(plan.analysis_failures)} file(s) "
                    f"(excluded from renaming):[/yellow]"
                )
                for name, reason in plan.analysis_failures:
                    _c.print(f"[yellow]  - {name}: {reason}[/yellow]")
            except ImportError:
                pass
        else:
            print(
                f"\n[ANALYSIS FAILURES] count={len(plan.analysis_failures)}"
            )
            for name, reason in plan.analysis_failures:
                print(f"  [skipped] {name}: {reason}")

    if not plan.validated_renames:
        click.echo("No renames proposed. All files appear to be well-named.")
        return

    # Update report with plan data
    total_tokens = {
        "input_tokens": plan.token_usage.input_tokens,
        "output_tokens": plan.token_usage.output_tokens,
    }
    report.update(
        "proposed",
        validated=plan.validated_renames,
        total_tokens=total_tokens,
        analysis_failures=plan.analysis_failures,
    )

    # Dry-run display
    validated = plan.validated_renames
    _display_dry_run(validated, use_rich=use_rich)

    if not execute and not headless:
        validated, execute = _interactive_review(validated)
        if not execute:
            click.echo("No changes made.")
            return

    did_execute = False

    if execute or (headless and not dry_run):
        # Update plan with user-reviewed renames (may have been modified)
        plan.validated_renames = validated

        with _phase_status(console, "Executing renames"):
            result = session.execute(plan)

        did_execute = True
        report.update("completed", executed=True, result=result)

        _display_execution_result(result, use_rich=use_rich)
        logger.info(f"Session {run_id} complete.")

    # Final report update for dry-run path
    if not did_execute:
        report.update("dry-run-complete")
    logger.info(f"Report: {report.report_path}")

    # --- Run Summary (logged for ALL runs including dry-run) ---
    total_token_count = plan.token_usage.total_tokens

    logger.info("=== RUN SUMMARY ===")
    logger.info(
        f"Files discovered: {discovery.impact.total_files} "
        f"({discovery.impact.supported_files} supported, "
        f"{discovery.impact.unsupported_files} unsupported)"
    )
    logger.info(f"Files analyzed: {discovery.impact.supported_files}")
    if plan.analysis_failures:
        logger.info(f"Analysis failures: {len(plan.analysis_failures)}")
    logger.info(
        f"Names proposed: {len(plan.validated_renames)} "
        f"({plan.total_renames} renames, "
        f"{plan.total_unchanged} unchanged)"
    )
    logger.info(
        f"Tokens: {plan.token_usage.input_tokens:,} input + "
        f"{plan.token_usage.output_tokens:,} output = "
        f"{total_token_count:,} total"
    )
    logger.info(f"Estimated cost: ${session._estimate_cost(plan.token_usage):.4f}")


@main.command()
@click.argument("target_directory", type=click.Path(exists=True), required=False)
@click.option("--force", "-f", is_flag=True, help="Undo without confirmation")
def undo(target_directory, force):
    """Undo the last rename operation."""
    target = Path(target_directory or ".").resolve()

    from ai_file_rename.executor import undo_renames

    if not force:
        if not click.confirm(f"Undo renames in {target}?", default=False):
            click.echo("Aborted.")
            return

    try:
        result = undo_renames(target)
        _display_execution_result(result)

        if result.failed == 0:
            click.echo("Undo complete. All files restored to original names.")
        else:
            click.echo(f"Undo completed with {result.failed} failures.")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--directory", "-d", default=None, help="Filter by target directory")
@click.option("--last", "-n", "last_n", default=10, type=int, help="Show last N sessions")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def history(directory, last_n, as_json):
    """View rename history."""
    import json

    config = load_config()
    run_id = generate_run_id()
    logger = RenameLogger(config.log_dir, run_id)

    dir_filter = Path(directory) if directory else None
    records = logger.query_history(directory=dir_filter, last_n=last_n)

    if not records:
        click.echo("No rename history found.")
        return

    if as_json:
        click.echo(json.dumps(records, indent=2, default=str))
    else:
        for record in records:
            click.echo(f"\n{'─'*50}")
            click.echo(f"Run:       {record.get('run_id', 'N/A')}")
            click.echo(f"Date:      {record.get('run_started_at', 'N/A')}")
            click.echo(f"Target:    {record.get('target_directory', 'N/A')}")
            click.echo(f"Renamed:   {record.get('files_renamed', 0)}")
            click.echo(f"Skipped:   {record.get('files_skipped', 0)}")
            click.echo(f"Failed:    {record.get('files_failed', 0)}")
