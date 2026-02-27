# Known + Open Issues

**Purpose:** Tracks implementation status and remaining work items for downstream agents.

---

### ISSUE-06: Stale Log File Accumulation

- **Priority:** LOW
- **Location:** `logger.py`

`RenameLogger.__init__()` creates a session log file immediately via `FileHandler`. Sessions that abort early (no API key, user cancels, no files found) leave 0-byte orphans. Mitigated by manual cleanup (`find ~/.ai-rename/logs/ -name "*.log" -empty -delete`). A proper fix would defer file creation until first log message (lazy file handler) or auto-clean on session end.

---

### ISSUE-08: Unit Tests for New Code Paths (2026-02-27)

- **Priority:** MODERATE
- **Location:** `tests/`

The improved `is_well_named()` heuristic, error-filtering in `name_folder()`, the `--no-skip-well-named` flag, and analysis failure reporting all lack dedicated unit tests. 312 existing tests pass but the new logic paths introduced on 2026-02-27 are not covered.

**Suggested test cases:**
- `is_well_named("presentation_final_v2_FINAL.pptx")` returns False (repeated word + version indicator)
- `is_well_named("file_with_bad_chars.txt")` returns False (generic filler word)
- `is_well_named("quarterly-revenue-report-2023.pdf")` returns True
- `name_folder()` with error-typed `AnalyzedFile` excludes it from naming
- `--no-skip-well-named` flag sets `config.skip_well_named = False`

---

### ISSUE-09: `test_undo_no_manifest` Pre-existing Test Failure

- **Priority:** LOW
- **Location:** `tests/test_cli.py`

The undo command returns exit code 0 when no manifest exists, but `test_undo_no_manifest` expects non-zero. Either update the test expectation or change the undo command to `sys.exit(1)` when no manifest is found.
