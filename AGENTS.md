# Agent Guide for ai-file-rename

> For AI agents operating or modifying this tool. Read this first, then load `docs/2-operations-manual.md` for the full CLI reference.
> Where any sentence here disagrees with the code under `src/ai_file_rename/`, the code is right and this file is the defect; fix it in the same change.

---

## Before You Start

**Load `docs/2-operations-manual.md` into your context.** It contains the complete CLI reference: all commands, flags, configuration options, supported file types, naming strategies, and cost management. Do not re-derive this information, it is already documented there.

This file covers only what is NOT in the operations manual: agent-specific workflows, integration patterns, and operational guidance.

---

## Working on the Code

Commands that run from a fresh clone (verified on Python 3.9 and 3.13):

```bash
uv sync --frozen --extra full --extra dev     # dev is an optional extra, not a dependency group
uv run --frozen pytest -q                      # 339 tests
uv run --frozen ruff check src tests
uv run --frozen ai-rename --help
```

Install the CLI for use rather than development: `uv tool install "ai-file-rename[full] @ ."` from the repo root (or the git URL once public). A `GEMINI_API_KEY` is required for any run that reaches Gemini; without one `ai-rename rename` prints an error and exits 1 before touching the target directory (it does create `~/.ai-rename/logs/` first, `logger.py`).

---

## Running the Tool Headlessly

The standard agent invocation:

```bash
ai-rename rename <target_directory> -r -x -H -P
```

Flags breakdown:
- `-r`: recursive (process subdirectories)
- `-x`: execute (actually rename files, not just dry-run)
- `-H`: headless (skip all interactive prompts)
- `-P`: plain output (structured text, no Rich formatting)

For a safe preview first:

```bash
ai-rename rename <target_directory> -r -d -H -P
```

`-d` overrides `-H`'s implicit execute: this gives you a dry-run with no prompts (`cli.py`, the `rename` command: `if dry_run: execute = False`, and execution runs only on `execute or (headless and not dry_run)`).

---

## Reading Results

After a run, **read the report file** in the target directory instead of parsing CLI stdout:

```
<target_directory>/.ai-rename-report-<run_id>.md
```

Find it with:

```bash
ls -t <target_directory>/.ai-rename-report-*.md | head -1
```

The report file is a markdown document with:
- A **Status** field showing the pipeline phase (`starting`, `discovered`, `analyzing`, `proposed`, `completed`, `dry-run-complete`)
- A **Mode** field showing `dry-run` or `executed`
- A markdown table of all proposed/executed renames
- Token usage and cost

**This is the authoritative record of what happened.** It is more reliable than parsing stdout because it is rewritten whole at each phase transition and contains structured data. The writer is `RunReport` in `cli.py`.

---

## Checking If a Run Is Still In Progress

The report file's **Status** field updates progressively. If you read it and see:

- `starting` or `discovered` or `analyzing`: the pipeline is still running, API calls in progress
- `proposed`: naming is done, execution may be pending
- `completed`: renames executed, run finished
- `dry-run-complete`: dry-run finished, no files modified

---

## Logs

Detailed per-file logs are written to `~/.ai-rename/logs/session-<run_id>.log`; every completed execution is appended to `~/.ai-rename/logs/rename-history.jsonl` and `session-ledger.csv` in the same directory (`logger.py`).

Log levels:
- **INFO**: per-file analysis results, per-file naming decisions, phase timing, run summary
- **DEBUG**: prompt details, Gemini response parsing, word tokenization steps
- **WARNING**: analysis failures, naming misses (files not found in Gemini response)

To get DEBUG output in the console, add `--verbose`:

```bash
ai-rename rename <dir> -r -x -H -P --verbose
```

---

## Undoing a Run

```bash
ai-rename undo <target_directory> -f
```

This reverses the renames recorded in the directory's manifest (`.ai-rename-manifest.json`). The manifest is deleted when a run completes with zero failures (`executor.py`, after the finalize step), so undo is available only for a run that was interrupted or had failures; after a clean run the command reports that there is nothing to undo, and the record of what moved is in `rename-history.jsonl`. **A headless re-run deletes an interrupted run's manifest without asking** (`cli.py`, the `existing.is_interrupted` block takes the discard branch when `-H` is set), so after an interruption run `undo` first, never a second `-H` pass.

---

## Key Behaviors to Be Aware Of

1. **Every processable file goes to Gemini, and every folder is named as a set.** There is no filename-based pre-filter and no single-file shortcut: one content-analysis call per file (`analyzer.py`), then the folder is named together, in one call for folders of up to 50 files and in clustered, sampled or progressive batches above that (`namer.py`, `select_strategy`). Files whose analysis came back as `error`, `unknown` or `skipped`, or with confidence below 0.1, are left out of the naming call and logged as `[skipped]` (`namer.py`, `name_folder`).

2. **Failed analysis = skipped, not corrupted.** If Gemini returns an error for a file (400, 429, etc.), that file is excluded from renaming entirely. It will appear in the report under "Analysis Failures."

3. **The tool writes to the target directory.** Two artifacts: the report file (`.ai-rename-report-*.md`, persists) and the manifest (`.ai-rename-manifest.json`, cleaned up on success). Both are dotfiles excluded from the tool's own discovery (`config.py`, `exclude_patterns`).

4. **The cost limit is a prompt, not a stop.** Default limit is $5.00 USD (`config.py`); override with `--cost-limit`. When the estimate exceeds it, an interactive run asks before continuing; a headless run (`-H`) prints the warning and continues (`cli.py`, the cost check confirms only when not headless), so `--cost-limit` does not bound an unattended run; bound it with `--max-files` or `--include` instead. The default model is `gemini-2.5-flash`; the cheapest is `gemini-2.0-flash` (`--model gemini-2.0-flash`; prices in `constants.py`, `COST_PER_TOKEN`).

---

## Documentation Map

| Document | What it covers | When to read |
|----------|---------------|--------------|
| `README.md` | The storefront: what it is, quickstart, a map into the modules | First contact |
| `docs/2-operations-manual.md` | Complete CLI reference, all flags, configuration, file types, naming strategies | Before operating the tool |
| `AGENTS.md` (this file) | Agent-specific workflows, integration patterns | Before operating the tool |
| `docs/1-known-issues.md` | Open items the code does not yet answer | Before contributing code |
| `docs/0-architecture.md` | Module design, data flow, pipeline architecture, written at design time | Before modifying code; the code wins where they differ |
| `docs/0-PRD.md` | Product requirements and the decisions behind the design, written at design time | For understanding design decisions |
