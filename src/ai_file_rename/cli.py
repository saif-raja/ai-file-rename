"""
CLI entrypoint for ai-file-rename.

Wires together the pipeline stages and manages interactive prompts.
The CLI calls pipeline functions in sequence but does NOT contain business logic.
"""

import asyncio
import contextlib
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

import click

from ai_file_rename import __version__
from ai_file_rename.config import Config, load_config
from ai_file_rename.logger import RenameLogger


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
    # Plain text fallback — structured for agent parsing
    print(f"[PHASE] {message} ...")
    yield
    print(f"[DONE]  {message}")


def _generate_run_id() -> str:
    """Generate a unique run ID: {date}-{short-uuid}."""
    date_part = datetime.now().strftime("%Y%m%d")
    uuid_part = uuid.uuid4().hex[:8]
    return f"{date_part}-{uuid_part}"


def _write_run_report(
    target: Path,
    run_id: str,
    config,
    discovery,
    validated: list,
    total_tokens: dict,
    skipped_well_named: list,
    skipped_analysis_failed: list,
    executed: bool,
    result=None,
) -> None:
    """Write a markdown run report to the target directory.

    Persists a human-readable summary of every run (dry-run or executed)
    so users can review what happened without re-running the tool.
    """
    from ai_file_rename.constants import COST_PER_TOKEN

    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    mode = "executed" if executed else "dry-run"
    model_costs = COST_PER_TOKEN.get(config.model, {})
    est_cost = (
        total_tokens.get("input_tokens", 0) * model_costs.get("input", 0)
        + total_tokens.get("output_tokens", 0) * model_costs.get("output", 0)
    )

    rename_count = sum(1 for v in validated if not v.original.is_unchanged)
    unchanged_count = sum(1 for v in validated if v.original.is_unchanged)

    lines = [
        "# ai-rename report",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Run ID | `{run_id}` |",
        f"| Timestamp | {timestamp} |",
        f"| Mode | **{mode}** |",
        f"| Target | `{target}` |",
        f"| Recursive | {'yes' if discovery.impact.recursive else 'no'} |",
        f"| Model | {config.model} |",
        "",
        "## Impact",
        "",
        f"- Files discovered: {discovery.impact.total_files} "
        f"({discovery.impact.supported_files} supported, "
        f"{discovery.impact.unsupported_files} unsupported)",
        f"- Files analyzed: {discovery.impact.supported_files - len(skipped_well_named)}",
        f"- Skipped (well-named): {len(skipped_well_named)}",
    ]

    if skipped_analysis_failed:
        lines.append(f"- Analysis failures: {len(skipped_analysis_failed)}")

    lines.extend([
        f"- Names proposed: {len(validated)} ({rename_count} renames, {unchanged_count} unchanged)",
        f"- Tokens: {total_tokens.get('input_tokens', 0):,} input + "
        f"{total_tokens.get('output_tokens', 0):,} output",
        f"- Estimated cost: ${est_cost:.4f}",
    ])

    if result:
        lines.extend([
            "",
            f"- Files renamed: {result.renamed}",
            f"- Files skipped: {result.skipped}",
            f"- Files failed: {result.failed}",
            f"- Symlinks updated: {result.symlinks_updated}",
        ])

    # Rename table
    lines.extend([
        "",
        "## Proposed Renames",
        "",
        "| # | Current Name | Proposed Name | Notes |",
        "|---|-------------|---------------|-------|",
    ])

    for i, v in enumerate(validated, 1):
        notes = ""
        if v.original.is_unchanged:
            notes = "unchanged"
        elif v.validation_notes:
            notes = "; ".join(v.validation_notes)
        lines.append(f"| {i} | {v.original.current_name} | {v.final_name} | {notes} |")

    # Well-named files
    if skipped_well_named:
        lines.extend([
            "",
            f"## Skipped (well-named): {len(skipped_well_named)} files",
            "",
        ])
        for name in skipped_well_named:
            lines.append(f"- {name}")

    # Analysis failures
    if skipped_analysis_failed:
        lines.extend([
            "",
            f"## Analysis Failures: {len(skipped_analysis_failed)} files",
            "",
        ])
        for name, reason in skipped_analysis_failed:
            lines.append(f"- **{name}**: {reason}")

    lines.append("")  # trailing newline

    report_path = target / f".ai-rename-report-{run_id}.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")


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
                f"  Already named:  {impact.already_well_named} (appear well-named)",
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

    # Plain text — structured key: value format for agent parsing
    print(f"\n[IMPACT ASSESSMENT]")
    print(f"target_directory: {impact.target_directory}")
    print(f"mode: {'recursive' if impact.recursive else 'single_folder'}")
    print(f"total_files: {impact.total_files}")
    print(f"supported_files: {impact.supported_files}")
    print(f"unsupported_files: {impact.unsupported_files}")
    print(f"already_well_named: {impact.already_well_named}")
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


def _display_dry_run(renames, use_rich: bool = True, skipped_well_named: list = None) -> None:
    """Display the proposed renames table and any skipped well-named files."""
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
        # Plain text — one line per rename, pipe-delimited for easy parsing
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

    # Display skipped well-named files
    if skipped_well_named:
        count = len(skipped_well_named)
        if rich_available:
            console.print(
                f"\n[dim]Skipped (already well-named): {count} file{'s' if count != 1 else ''}[/dim]"
            )
            for name in skipped_well_named:
                console.print(f"[dim]  - {name}[/dim]")
        else:
            print(f"\nSkipped (already well-named): {count} file{'s' if count != 1 else ''}")
            for name in skipped_well_named:
                print(f"  - {name}")


def _interactive_review(
    validated: list,
) -> tuple[list, bool]:
    """
    Interactive dry-run review with Approve/Reject/Edit/Save options.

    Returns:
        Tuple of (possibly-modified validated list, should_execute bool).
    """
    click.echo("\n" + "─" * 60)
    click.echo(" [A] Approve all    — execute all proposed renames")
    click.echo(" [R] Reject all     — abort, no changes")
    click.echo(" [E] Edit           — review each file individually")
    click.echo(" [S] Save & quit    — save plan to JSON for later")
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
            click.echo(f"  [{i}/{len(validated)}] {current} — unchanged, skipping")
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

    # Plain text — structured for agent parsing
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
@click.option("--no-skip-well-named", is_flag=True, default=False,
              help="Disable the well-named heuristic — analyze ALL files regardless of current name.")
def rename(target_directory, recursive, execute, headless, config_path, model,
           max_files, custom_instructions, verbose, cost_limit,
           dry_run, include, exclude, skip_converted, log_level, plain,
           no_skip_well_named):
    """Rename files using AI-powered content analysis."""
    # Build CLI overrides
    overrides = {}
    if model is not None:
        overrides["model"] = model
    if max_files is not None:
        overrides["max_files"] = max_files
    if custom_instructions is not None:
        overrides["custom_instructions"] = custom_instructions
    if cost_limit is not None:
        overrides["cost_limit"] = cost_limit
    if headless:
        overrides["require_confirmation"] = False
    if include is not None:
        overrides["include_patterns"] = [include]
    if exclude is not None:
        overrides["exclude_patterns"] = [exclude]
    if skip_converted:
        overrides["convert_office_docs"] = False
    if log_level is not None:
        overrides["log_level"] = log_level.upper()
    if no_skip_well_named:
        overrides["skip_well_named"] = False

    # --dry-run explicitly disables execute mode
    if dry_run:
        execute = False

    # Load config
    cfg_path = Path(config_path) if config_path else None
    config = load_config(config_path=cfg_path, cli_overrides=overrides)

    if not config.gemini_api_key and not config.use_vertex_ai:
        click.echo(
            "Error: No API key found. Set GEMINI_API_KEY environment variable "
            "or add it to ~/.ai-rename.yaml",
            err=True,
        )
        sys.exit(1)

    run_id = _generate_run_id()
    logger = RenameLogger(config.log_dir, run_id, verbose=verbose)
    target = Path(target_directory).resolve()

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
                    validated = ValidatedRename(
                        original=proposed,
                        final_name=entry["new_name"],
                        validation_notes=["Resumed from manifest"],
                    )
                    resumed_renames.append(validated)

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
                logger.info(f"Resume session {run_id} complete.")
                return
            elif choice == "discard":
                existing.cleanup()
        else:
            existing.cleanup()

    # --plain or --headless both disable Rich rendering
    use_rich = not plain and not headless
    console = _get_console(plain=not use_rich)

    # Phase 1: Discovery
    from ai_file_rename.discovery import discover

    try:
        with _phase_status(console, "Discovering files"):
            discovery = discover(target, recursive, config)
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    _display_impact_summary(discovery.impact, use_rich=use_rich)

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

    # Phase 2: Preprocessing
    from ai_file_rename.preprocessing import preprocess
    from ai_file_rename.validator import is_well_named

    with tempfile.TemporaryDirectory(prefix="ai-rename-") as tmp:
        tmp_dir = Path(tmp)

        processable_files = [
            f for f in discovery.files
            if f.category.value != "unsupported"
        ]

        # Filter out already well-named files to save API calls
        skipped_well_named = []
        if config.skip_well_named:
            filtered = []
            for f in processable_files:
                if is_well_named(f.name):
                    skipped_well_named.append(f.name)
                else:
                    filtered.append(f)
            if skipped_well_named:
                logger.info(
                    f"Skipping {len(skipped_well_named)} already well-named files"
                )
            processable_files = filtered

        logger.info(f"Preprocessing {len(processable_files)} files...")
        with _phase_status(console, f"Preprocessing {len(processable_files)} files"):
            enriched = preprocess(processable_files, tmp_dir, config)

        # Phase 3: Context building
        from ai_file_rename.context import build_context

        logger.info("Building folder context...")
        with _phase_status(console, "Building folder context"):
            folder_contexts = build_context(enriched, target)

        # Phase 4: Content analysis
        from ai_file_rename.analyzer import analyze_all

        logger.info("Analyzing file contents with Gemini...")

        try:
            from google import genai
            if config.use_vertex_ai:
                client = genai.Client(
                    vertexai=True,
                    project=config.vertex_project,
                    location=config.vertex_location,
                )
            else:
                client = genai.Client(api_key=config.gemini_api_key)
        except ImportError:
            click.echo(
                "Error: google-genai package not installed. "
                "Run: pip install google-genai",
                err=True,
            )
            sys.exit(1)

        t_analysis_start = time.monotonic()
        with _phase_status(console, "Analyzing file contents with Gemini"):
            analyzed, analyze_tokens = asyncio.run(
                analyze_all(
                    folder_contexts,
                    client,
                    config.model,
                    config,
                    concurrency=config.concurrency,
                    logger=logger,
                )
            )
        t_analysis_elapsed = time.monotonic() - t_analysis_start
        analyzed_count = sum(len(v) for v in analyzed.values())
        logger.info(
            f"Phase: Content Analysis — {analyzed_count} files "
            f"in {t_analysis_elapsed:.1f}s"
        )

        # Phase 5: Holistic naming
        from ai_file_rename.namer import name_all

        logger.info("Generating holistic names...")
        t_naming_start = time.monotonic()
        with _phase_status(console, "Generating holistic names"):
            proposed, naming_tokens = asyncio.run(
                name_all(
                    analyzed,
                    folder_contexts,
                    client,
                    config.model,
                    config,
                    concurrency=config.concurrency,
                    logger=logger,
                )
            )
        t_naming_elapsed = time.monotonic() - t_naming_start
        naming_count = sum(len(v) for v in proposed.values())
        logger.info(
            f"Phase: Holistic Naming — {naming_count} names "
            f"across {len(proposed)} folders in {t_naming_elapsed:.1f}s"
        )

        total_tokens = {
            "input_tokens": analyze_tokens["input_tokens"] + naming_tokens["input_tokens"],
            "output_tokens": analyze_tokens["output_tokens"] + naming_tokens["output_tokens"],
        }
        logger.info(
            f"Token usage — input: {total_tokens['input_tokens']:,}, "
            f"output: {total_tokens['output_tokens']:,}"
        )

    # Report files that failed analysis (ISSUE-01: these are excluded from
    # naming to prevent error messages from leaking into filenames)
    skipped_analysis_failed = []
    for folder_path, analyzed_files in analyzed.items():
        for af in analyzed_files:
            ct = af.summary.content_type
            if ct in ("error", "unknown", "skipped") or af.summary.confidence < 0.1:
                reason = af.summary.primary_subject[:80]
                skipped_analysis_failed.append((af.enriched.entry.name, reason))
                logger.warning(
                    f"Analysis failed for {af.enriched.entry.name}: {reason}"
                )

    if skipped_analysis_failed:
        if use_rich:
            try:
                from rich.console import Console as _C
                _c = _C()
                _c.print(
                    f"\n[yellow]Analysis failed for "
                    f"{len(skipped_analysis_failed)} file(s) "
                    f"(excluded from renaming):[/yellow]"
                )
                for name, reason in skipped_analysis_failed:
                    _c.print(f"[yellow]  - {name}: {reason}[/yellow]")
            except ImportError:
                pass
        else:
            print(
                f"\n[ANALYSIS FAILURES] count={len(skipped_analysis_failed)}"
            )
            for name, reason in skipped_analysis_failed:
                print(f"  [skipped] {name}: {reason}")

    # Flatten all proposed renames
    all_renames = []
    for folder_path, renames_list in proposed.items():
        all_renames.extend(renames_list)

    if not all_renames:
        click.echo("No renames proposed. All files appear to be well-named.")
        return

    # Phase 6: Validation
    from ai_file_rename.validator import validate_renames

    logger.info(f"Validating {len(all_renames)} proposed renames...")
    existing_files = {f.name for f in discovery.files}
    files_being_renamed = {r.current_name for r in all_renames}

    with _phase_status(console, f"Validating {len(all_renames)} proposed renames"):
        validated = validate_renames(
            all_renames,
            symlink_map=discovery.symlink_map,
            existing_files=existing_files,
            files_being_renamed=files_being_renamed,
        )

    # Phase 7: Dry-run display
    _display_dry_run(validated, use_rich=use_rich, skipped_well_named=skipped_well_named)

    if not execute and not headless:
        validated, execute = _interactive_review(validated)
        if not execute:
            click.echo("No changes made.")
            return

    if execute or (headless and not dry_run):
        # Phase 8: Execution
        from ai_file_rename.executor import execute_renames

        logger.info("Executing renames...")
        with _phase_status(console, "Executing renames"):
            result = execute_renames(
                validated,
                manifest_dir=target,
                run_id=run_id,
                config=config,
                symlink_map=discovery.symlink_map,
            )

        # Attach token usage and cost estimate to result (ISSUE-07: these
        # were previously 0 in the CSV ledger because they weren't set)
        from ai_file_rename.constants import COST_PER_TOKEN

        result.total_tokens_used = (
            total_tokens["input_tokens"] + total_tokens["output_tokens"]
        )
        model_costs = COST_PER_TOKEN.get(config.model, {})
        result.estimated_cost_usd = round(
            total_tokens["input_tokens"] * model_costs.get("input", 0.0)
            + total_tokens["output_tokens"] * model_costs.get("output", 0.0),
            4,
        )

        _display_execution_result(result, use_rich=use_rich)

        # Write to global history
        history_record = {
            "run_id": run_id,
            "run_started_at": result.started_at.isoformat(),
            "run_completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "target_directory": str(target),
            "recursive": recursive,
            "model_used": config.model,
            "files_discovered": discovery.impact.total_files,
            "files_renamed": result.renamed,
            "files_skipped": result.skipped,
            "files_failed": result.failed,
            "symlinks_updated": result.symlinks_updated,
            "renames": [
                {"old": r.old_path.name, "new": r.new_path.name}
                for r in result.results
                if r.status == "completed"
            ],
        }
        logger.append_to_history(history_record)

        # Write to CSV session ledger
        duration = None
        if result.started_at and result.completed_at:
            duration = round(
                (result.completed_at - result.started_at).total_seconds(), 2
            )
        logger.append_to_csv_ledger({
            "timestamp": (
                result.completed_at.isoformat()
                if result.completed_at
                else result.started_at.isoformat()
            ),
            "run_id": run_id,
            "target_directory": str(target),
            "recursive": recursive,
            "total_files_discovered": discovery.impact.total_files,
            "total_folders_touched": discovery.impact.folders_affected,
            "files_renamed": result.renamed,
            "files_skipped": result.skipped,
            "files_failed": result.failed,
            "symlinks_updated": result.symlinks_updated,
            "model_used": config.model,
            "estimated_tokens": result.total_tokens_used,
            "estimated_cost_usd": result.estimated_cost_usd,
            "duration_seconds": duration,
        })

        logger.info(f"Session {run_id} complete.")

    # --- Write run report to target directory ---
    _did_execute = 'result' in dir() and result is not None
    _analysis_failed = skipped_analysis_failed if 'skipped_analysis_failed' in dir() else []
    _write_run_report(
        target=target,
        run_id=run_id,
        config=config,
        discovery=discovery,
        validated=validated,
        total_tokens=total_tokens,
        skipped_well_named=skipped_well_named,
        skipped_analysis_failed=_analysis_failed,
        executed=_did_execute,
        result=result if _did_execute else None,
    )
    logger.info(f"Report written to {target / f'.ai-rename-report-{run_id}.md'}")

    # --- Run Summary (logged for ALL runs including dry-run) ---
    analysis_failed_count = len(_analysis_failed)
    well_named_count = len(skipped_well_named)
    total_token_count = total_tokens["input_tokens"] + total_tokens["output_tokens"]

    logger.info("=== RUN SUMMARY ===")
    logger.info(
        f"Files discovered: {discovery.impact.total_files} "
        f"({discovery.impact.supported_files} supported, "
        f"{discovery.impact.unsupported_files} unsupported)"
    )
    logger.info(
        f"Files analyzed: {len(processable_files)} "
        f"({well_named_count} skipped well-named)"
    )
    if analysis_failed_count:
        logger.info(f"Analysis failures: {analysis_failed_count}")
    logger.info(
        f"Names proposed: {len(all_renames)} "
        f"({sum(1 for v in validated if not v.original.is_unchanged)} renames, "
        f"{sum(1 for v in validated if v.original.is_unchanged)} unchanged)"
    )
    logger.info(
        f"Tokens: {total_tokens['input_tokens']:,} input + "
        f"{total_tokens['output_tokens']:,} output = "
        f"{total_token_count:,} total"
    )
    from ai_file_rename.constants import COST_PER_TOKEN as _CPT
    _mc = _CPT.get(config.model, {})
    _est_cost = (
        total_tokens["input_tokens"] * _mc.get("input", 0)
        + total_tokens["output_tokens"] * _mc.get("output", 0)
    )
    logger.info(f"Estimated cost: ${_est_cost:.4f}")


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
    run_id = _generate_run_id()
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
