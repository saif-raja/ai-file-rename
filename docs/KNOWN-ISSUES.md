# Known + Open Issues

**Purpose:** Tracks open work items for downstream agents. Prioritized by severity.

**E2E test folders** (in `~/Documents/`, copied from `tests/fixtures/sample-files/`):
- `~/Documents/ai-rename-e2e-test/` — dry-run test copy (original files intact)
- `~/Documents/ai-rename-e2e-execute-test/` — executed run (files renamed)

---

## Critical / High Priority

### ISSUE-13: Gemini File Upload Resource Leak

- **Severity:** HIGH
- **Location:** `analyzer.py:269-278`

Files uploaded to Gemini File API via `client.files.upload()` are never cleaned up with `client.files.delete()`. Each run accumulates files on Gemini's servers, eventually hitting quota limits.

**Fix:** Add `client.files.delete(name=uploaded.name)` in a `finally` block after `generate_content()`.

---

### ISSUE-14: Silent Failure in `name_all()` Exception Handler

- **Severity:** HIGH
- **Location:** `namer.py:774`

The `except Exception` block in `name_all()` silently swallows errors and sets `results[folder_path] = []`. The user gets no indication that naming failed for an entire folder.

**Fix:** Log the exception at ERROR level: `logger.error(f"Naming failed for {folder_path}: {e}")`.

---

### ISSUE-15: Broken Collision Detection in `validate_renames()`

- **Severity:** HIGH
- **Location:** `validator.py:351`

The `collision_resolved` flag compares `rename.proposed_name` (already sanitized) against `sanitize_and_build_name(original.proposed_name)` — but `rename` IS the sanitized version of `original`, so this comparison is always False. Collision detection is effectively a no-op.

**Fix:** Store the pre-sanitization proposed name and compare against it, or compute collision resolution by checking whether the name was changed by `resolve_collisions()` / `check_existing_collisions()`.

---

### ISSUE-16: CLI Reimplements Session API Pipeline (Root Cause of 7 Duplications)

- **Severity:** HIGH (architecture)
- **Location:** `cli.py` (entire `rename` command)

`cli.py` re-implements the full `RenameSession.analyze()` + `RenameSession.execute()` pipeline inline (~400 lines) rather than delegating. This is the root cause of duplicated: run ID generation, Gemini client init, cost estimation (4 copies), history writing, CSV ledger writing. The CLI docstring says "does NOT contain business logic" — but it does.

**Fix:** Refactor `cli.py` to use `RenameSession` for the pipeline, keeping only CLI-specific concerns (prompts, display, RunReport).

---

## Medium Priority

### ISSUE-17: Dead Code Across Codebase

- **Severity:** MEDIUM
- **Location:** Multiple files

| Dead Code | File | Why It's Dead |
|-----------|------|---------------|
| `_name_single_file()` | `namer.py:585-651` | No longer called after LLM-first refactor |
| `_read_text_content()` | `preprocessing.py:99-110` | Never called by `preprocess()` |
| `CONVERSION_MAP` | `constants.py:232-246` | Never imported; `preprocessing.py` has its own dispatch |
| `METADATA_EXTRACTORS_MAP` | `constants.py:514-549` | Never imported; `metadata.py` has its own `EXTRACTORS` |
| `DEFAULT_PATTERNS` | `constants.py:290-316` | Never imported; `validator.py` has its own inline list |

**Fix:** Remove all five. The dead constants in `constants.py` are especially dangerous — they've already drifted out of sync with the actual dispatch tables.

---

### ISSUE-18: Exact-Duplicate Helper Functions

- **Severity:** MEDIUM
- **Location:** Multiple files

| Function | Location A | Location B | Action |
|----------|-----------|-----------|--------|
| `_extract_token_counts()` | `analyzer.py:43` | `namer.py:56` | Move to shared utility |
| `_add_token_counts()` | `analyzer.py:57` | `namer.py:70` | Move to shared utility |
| `_generate_run_id()` | `cli.py:63` | `session.py:41` | Import from session |
| `_build_breadcrumb()` | `discovery.py:76` | `context.py:13` | Import from context |
| `_calculate_depth()` | `discovery.py:90` | `context.py:27` | Import from context |

---

### ISSUE-19: Config Loading Silently Ignores Malformed YAML

- **Severity:** MEDIUM
- **Location:** `config.py:73-96`

If `~/.ai-rename.yaml` exists but is malformed, the error is silently swallowed and defaults are used. The user has no way to know their config was ignored.

**Fix:** Catch `yaml.YAMLError` and emit a warning.

---

### ISSUE-20: Symlink Atomic Update Race Condition

- **Severity:** MEDIUM
- **Location:** `executor.py:100-103`

The temp symlink path `.ai-rename-tmp` can collide if a previous run crashed or two instances run concurrently, causing `FileExistsError`.

**Fix:** Use PID-qualified temp name: `symlink.with_suffix(f".ai-rename-tmp-{os.getpid()}")` and clean up in a `finally` block.

---

## Low Priority

### ISSUE-12: `file with lots of spaces.txt` Classified as Well-Named

- **Severity:** LOW
- **Location:** `validator.py`

The `is_well_named()` heuristic doesn't detect excessive whitespace as a quality signal. LOW priority because the LLM-first naming approach handles these files regardless.

---

### ISSUE-21: Path Traversal via Symlinks Outside Target Directory

- **Severity:** LOW (requires elevated privileges to be exploitable)
- **Location:** `discovery.py:191-194`

No validation that discovered files (via symlinks) stay within the target directory boundary. A symlink to `../../etc/passwd` would be followed.

**Fix:** Resolve each path and check `resolved.relative_to(target_dir)`.

---

### ISSUE-22: Metadata Extraction Timeout Ineffective on Windows

- **Severity:** LOW
- **Location:** `metadata.py:74-111`

`_with_timeout()` uses `threading.Thread` on Windows, but Python threads cannot be forcibly killed. A corrupt file causing an extractor to hang will block indefinitely.

---

### ISSUE-23: Default Name Pattern Lists Have Diverged

- **Severity:** LOW
- **Location:** `constants.py:290` vs `validator.py:411`

`constants.py` `DEFAULT_PATTERNS` and `validator.py`'s inline list have patterns the other doesn't. `constants.py` version is dead code (never imported). If consolidated, the union of both lists would provide better coverage.
