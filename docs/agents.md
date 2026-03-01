# Agent Guide for ai-file-rename

> For AI agents operating this tool. Read this first, then load `docs/operations-manual.md` for full CLI reference.

---

## Before You Start

**Load `docs/operations-manual.md` into your context.** It contains the complete CLI reference: all commands, flags, configuration options, supported file types, naming strategies, and cost management. Do not re-derive this information — it is already documented there.

This file covers only what is NOT in the operations manual: agent-specific workflows, integration patterns, and operational guidance.

---

## Running the Tool Headlessly

The standard agent invocation:

```bash
ai-rename rename <target_directory> -r -x -H -P
```

Flags breakdown:
- `-r` — recursive (process subdirectories)
- `-x` — execute (actually rename files, not just dry-run)
- `-H` — headless (skip all interactive prompts)
- `-P` — plain output (structured text, no Rich formatting)

For a safe preview first:

```bash
ai-rename rename <target_directory> -r -d -H -P
```

`-d` overrides `-H`'s implicit execute — this gives you a dry-run with no prompts.

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

**This is the authoritative record of what happened.** It is more reliable than parsing stdout because it is written atomically and contains structured data.

---

## Checking If a Run Is Still In Progress

The report file's **Status** field updates progressively. If you read it and see:

- `starting` or `discovered` or `analyzing` — the pipeline is still running, API calls in progress
- `proposed` — naming is done, execution may be pending
- `completed` — renames executed, run finished
- `dry-run-complete` — dry-run finished, no files modified

---

## Logs

Detailed per-file logs are written to `~/.ai-rename/logs/session-<run_id>.log`.

Log levels:
- **INFO** — per-file analysis results, per-file naming decisions, phase timing, run summary
- **DEBUG** — prompt details, Gemini response parsing, word tokenization steps
- **WARNING** — analysis failures, naming misses (files not found in Gemini response)

To get DEBUG output in the console, add `--verbose`:

```bash
ai-rename rename <dir> -r -x -H -P --verbose
```

---

## Undoing a Run

```bash
ai-rename undo <target_directory> -f
```

This reverses the last executed rename operation using the stored manifest. Only works if the manifest file (`.ai-rename-manifest.json`) is still present — it is deleted after successful completion, so undo is only available if the run failed partway through.

---

## Key Behaviors to Be Aware Of

1. **Well-named files are skipped by default.** Files with descriptive names (3+ meaningful words, no version indicators, no auto-generated patterns) are not sent to the API. Use `--no-skip-well-named` to override.

2. **Failed analysis = skipped, not corrupted.** If Gemini returns an error for a file (400, 429, etc.), that file is excluded from renaming entirely. It will appear in the report under "Analysis Failures."

3. **Single-file folders skip the naming API call.** When a folder has exactly 1 processable file, the name is derived deterministically from the content analysis — no holistic naming LLM call. This saves cost.

4. **The tool writes to the target directory.** Two artifacts: the report file (`.ai-rename-report-*.md`, persists) and the manifest (`.ai-rename-manifest.json`, cleaned up on success). Both are dotfiles excluded from the tool's own discovery.

5. **Cost is controlled.** Default limit is $5.00 USD. Override with `--cost-limit`. The cheapest model is `gemini-2.0-flash` (`--model gemini-2.0-flash`).

---

## Documentation Map

| Document | What it covers | When to read |
|----------|---------------|--------------|
| `docs/operations-manual.md` | Complete CLI reference, all flags, configuration, file types, naming strategies | Before operating the tool |
| `docs/agents.md` (this file) | Agent-specific workflows, integration patterns | Before operating the tool |
| `docs/KNOWN-ISSUES.md` | Open bugs and tracked issues | Before contributing code |
| `docs/ARCHITECTURE.md` | Module design, data flow, pipeline architecture | Before modifying code |
| `docs/PRD.md` | Product requirements and design rationale | For understanding design decisions |
