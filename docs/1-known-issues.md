# Known + Open Issues

**Purpose:** Tracks open work items for downstream agents. Prioritized by severity.

**E2E test folders** (in `~/Documents/`, copied from `tests/fixtures/sample-files/`):
- `~/Documents/ai-rename-e2e-test/` — dry-run test copy (original files intact)
- `~/Documents/ai-rename-e2e-execute-test/` — executed run (files renamed)

---

## Open — Large Effort (Architectural)

### ISSUE-16: CLI Reimplements Session API Pipeline (Root Cause of 7 Duplications)

- **Severity:** HIGH (architecture)
- **Location:** `cli.py` (entire `rename` command, ~471 lines within a 1070-line file)
- **Cascade:** Resolving this would also resolve parts of ISSUE-18 (the `_generate_run_id()` duplicate).

`cli.py` re-implements the full `RenameSession.analyze()` + `RenameSession.execute()` pipeline inline rather than delegating. This is the root cause of duplicated: run ID generation, Gemini client init, cost estimation (4 copies), history writing, CSV ledger writing. The CLI docstring says "does NOT contain business logic" — but it does.

**Fix:** Refactor `cli.py` to use `RenameSession` for the pipeline, keeping only CLI-specific concerns (prompts, display, RunReport).

#### Verified Reconnaissance (from 2026-03-02 session)

**Current state of cli.py `rename()` — the inline pipeline (lines 680–1010):**

The `rename()` function directly imports and calls every pipeline stage in sequence:

| Phase | CLI line | Import | What it does |
|-------|---------|--------|-------------|
| Discovery | 680 | `from discovery import discover` | `discover(target, recursive, config)` |
| Preprocessing | 714 | `from preprocessing import preprocess` | `preprocess(processable_files, tmp_dir, config)` |
| Context | 751 | `from context import build_context` | `build_context(enriched, target)` |
| Analysis | 758 | `from analyzer import analyze_all` | `asyncio.run(analyze_all(...))` |
| Naming | 800 | `from namer import name_all` | `asyncio.run(name_all(...))` |
| Validation | 864 | `from validator import validate_renames` | `validate_renames(...)` |
| Execution | 901 | `from executor import execute_renames` | `execute_renames(...)` |

This is the **exact same sequence** as `RenameSession.analyze()` (session.py lines 174–339) + `RenameSession.execute()`.

**`RenameSession` (session.py, 468 lines) already implements the full pipeline:**
- `analyze()` → returns `RenamePlan` (discovery through validation)
- `execute(plan)` → returns `ExecutionResult`
- Has its own `_get_client()`, `_estimate_cost()`, `_record_history()`, `_record_csv_ledger()`

**`cli.py` does NOT import or use `RenameSession` at all.** There is zero reference to it.

**What MUST stay in cli.py (CLI-specific concerns):**
- `RunReport` class (lines 70–210) — stateful markdown report, rewritten at each phase
- `_display_impact_summary()` — Rich/plain impact assessment display
- `_display_dry_run()` — Rich/plain proposed renames table
- `_interactive_review()` — approve/reject/edit/save menu (lines 343–457)
- `_edit_individually()` — per-file accept/reject/custom name
- `_display_execution_result()` — Rich/plain execution summary
- `_phase_status()` — Rich spinner context manager
- `click.confirm()` calls — cost check, proceed confirmation
- Crash recovery / manifest resume prompts (lines 608–670)

**What SHOULD move to Session (or be deleted from CLI):**
- Gemini client initialization (cli.py lines 762–778 duplicates `session._get_client()`)
- `_generate_run_id()` (cli.py line 63 duplicates session.py line 40)
- Cost estimation logic (cli.py lines 924–934 duplicates `session._estimate_cost()`)
- History + CSV ledger writing (cli.py lines 940–995 duplicates `session._record_history()` + `session._record_csv_ledger()`)

**Booby traps and pitfalls:**
1. **`RunReport` depends on intermediate state.** The report is updated at each phase transition (`report.update("discovered", ...)`, `report.update("analyzing", ...)`, etc.). If cli.py delegates to `RenameSession.analyze()` which returns a single `RenamePlan`, the CLI loses visibility into intermediate progress. The Session would need to expose phase callbacks or events.
2. **`asyncio.run()` calls.** The CLI wraps async pipeline stages with `asyncio.run()` (lines 790, 800). The Session also does this internally. If the CLI calls Session, there can't be nested `asyncio.run()` calls — the Session's async internals need to be invoked from within the same event loop, or the Session needs to handle the event loop itself.
3. **Interactive prompts happen MID-pipeline.** Between discovery and preprocessing, there's a `click.confirm("Proceed with content analysis?")` (line 698). Between validation and execution, there's the full interactive review menu. The Session API would need to expose "checkpoints" where the CLI can interject with user prompts, or the pipeline must be split into analyze → (user review) → execute, which `RenamePlan` already enables.
4. **The `skipped_well_named` filter was removed in this session.** Both cli.py and session.py previously had filtering logic here. It's now gone from both, simplifying the refactor.

---

### ISSUE-18: Exact-Duplicate Helper Functions

- **Severity:** MEDIUM
- **Location:** Multiple files

| Function | Location A | Location B | Action |
|----------|-----------|-----------|--------|
| `_extract_token_counts()` | `analyzer.py:43` | `namer.py:56` | Move to shared utility |
| `_add_token_counts()` | `analyzer.py:57` | `namer.py:70` | Move to shared utility |
| `_generate_run_id()` | `cli.py:63` | `session.py:40` | Import from session (or delete from CLI if ISSUE-16 is resolved first) |
| `_build_breadcrumb()` | `discovery.py:75` | `context.py:13` | Import from context |
| `_calculate_depth()` | `discovery.py:89` | `context.py:27` | Import from context |

#### Verified Reconnaissance (from 2026-03-02 session)

**All 5 pairs were verified as byte-for-byte identical implementations.** No drift between copies.

**Recommended consolidation order:**

1. **`_build_breadcrumb` + `_calculate_depth`** (easiest, zero risk): The canonical home is `context.py` since that's the module's purpose. Change `discovery.py` to `from ai_file_rename.context import _build_breadcrumb, _calculate_depth` and delete the local copies. No circular import risk — discovery doesn't import context, and context doesn't import discovery.

2. **`_extract_token_counts` + `_add_token_counts`** (easy, needs new home): Neither analyzer.py nor namer.py is the natural owner. Create a small `utils.py` or add to an existing shared module. Both analyzer.py and namer.py would import from it. No circular import risk.

3. **`_generate_run_id`** (depends on ISSUE-16): If ISSUE-16 is resolved first, cli.py stops needing this function entirely (Session generates the run ID). If ISSUE-16 is NOT resolved, cli.py should import from session.py. No circular import risk — cli.py already doesn't import session.py, and session.py doesn't import cli.py.

**Booby traps and pitfalls:**
1. **Test imports may reference the old locations.** After moving functions, grep ALL test files for imports of the moved functions from their old locations. Tests import `_extract_token_counts` from both `analyzer` and `namer` in some test files.
2. **The functions are module-private (leading underscore).** Moving them to a shared module means making them importable — consider dropping the underscore or keeping it with explicit `__all__` exports.
3. **Line numbers in this doc are approximate.** The codebase has been modified during this session (dead code removal, is_well_named removal, bug fixes). Always verify current line numbers before editing.

---

## Session Context for Future Agent

**Test suite status:** 328 tests passing, 0 failures (as of end of session).

**Changes made this session (uncommitted):**
- Fixed ISSUE-13 (Gemini upload cleanup), ISSUE-14 (error logging), ISSUE-17 (dead code), ISSUE-19 (YAML crash), ISSUE-20 (symlink race)
- Removed `is_well_named()` heuristic entirely (ISSUE-12 closed)
- Closed ISSUE-15, ISSUE-21, ISSUE-22, ISSUE-23 as invalid or resolved
- Added 13 new tests, removed 47 dead tests
- Net diff: +484 / -777 lines across 25 files

**Approach recommendation for ISSUE-16 + ISSUE-18:**
- Tackle ISSUE-18 pairs 1 and 2 first (breadcrumb/depth and token helpers) — these are independent of ISSUE-16 and reduce noise before the big refactor
- Then tackle ISSUE-16 (CLI refactor) which will naturally resolve pair 3 (`_generate_run_id`)
- Use planning mode before starting ISSUE-16 — the interactive prompt checkpoints and RunReport phase updates are the hardest design decisions
