# Known + Open Issues

**Purpose:** Tracks implementation status and remaining work items for downstream agents.

**E2E test folders** (in `~/Documents/`, copied from `tests/fixtures/sample-files/`):
- `~/Documents/ai-rename-e2e-test/` — dry-run test copy (original files intact)
- `~/Documents/ai-rename-e2e-execute-test/` — executed run (files renamed, report at `.ai-rename-report-20260301-6614ff09.md`)

---

### ISSUE-06: Stale Log File Accumulation

- **Priority:** LOW
- **Location:** `logger.py`

`RenameLogger.__init__()` creates a session log file immediately via `FileHandler`. Sessions that abort early (no API key, user cancels, no files found) leave 0-byte orphans. Mitigated by manual cleanup (`find ~/.ai-rename/logs/ -name "*.log" -empty -delete`). A proper fix would defer file creation until first log message (lazy file handler) or auto-clean on session end.

---

### ISSUE-09: `test_undo_no_manifest` Pre-existing Test Failure

- **Priority:** LOW
- **Location:** `tests/test_cli.py`

The undo command returns exit code 0 when no manifest exists, but `test_undo_no_manifest` expects non-zero. Either update the test expectation or change the undo command to `sys.exit(1)` when no manifest is found.
