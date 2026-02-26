# Known Issues & Implementation Gaps

**Generated:** 2026-02-26
**Source:** Critical analysis of PRD.md and ARCHITECTURE.md against implemented codebase
**Purpose:** Actionable issue tracker for downstream agents. Each issue is self-contained with enough context to implement without re-reading the full PRD.
**Status Key:** `MISSING` = no code exists | `PARTIAL` = structure exists but behavior incomplete | `IMPLEMENTED` = resolved


## How To Use This Document

1. Issues are ordered by priority (Critical → Moderate → Minor)
2. Each issue has a unique ID (e.g., `GAP-01`) for cross-referencing
3. Each issue includes: what the PRD requires, what currently exists, what's missing, and which files to modify
4. When an issue is resolved, change its status to `IMPLEMENTED` and add the date
5. Agents should work through Critical gaps first, in order

---

## All Gaps Resolved

All gaps identified in the initial audit have been implemented and verified.

### GAP-10: Edge Cases from PRD Section 19
- **Status:** `IMPLEMENTED` (2026-02-26)
- **Implementation:**
  | Edge Case | How It Works |
  |-----------|-------------|
  | File locked by another process | `_is_locked_file_error()` in executor.py detects `PermissionError`/`EACCES`, skips file, continues batch. Manifest records as "failed", result counts as "skipped" (different views: mechanical vs user-facing). |
  | File modified during processing | `_get_mtime()` in analyzer.py captures mtime before API call, compares after; skips if changed. |
  | Target directory is network drive | `_is_network_drive()` in executor.py checks `st_dev` mismatch; warning is stored in `ExecutionResult.warnings` and displayed in CLI output. |
  | Gemini returns invalid JSON (retry) | One retry in `_analyze_single_file()` before regex fallback; retry also passes `response_json_schema`. |
- **Files Modified:** `executor.py`, `analyzer.py`, `models.py` (added `warnings` field to `ExecutionResult`)
- **Tests:** 11 tests across `test_executor.py` and `test_analyzer.py`

### GAP-11: Gemini response_schema Parameter
- **Status:** `IMPLEMENTED` (2026-02-26)
- **Implementation:** JSON schema generated from `ContentSummary` via Pydantic `model_json_schema()` and a hand-crafted naming response schema. Both passed as `response_json_schema` config parameter. Verified compatible with installed `google-genai` v1.65.0.
- **Files Modified:** `analyzer.py`, `namer.py`
- **Tests:** 4 tests verifying schema structure and API call inclusion

### GAP-12: Vertex AI Client Initialization
- **Status:** `IMPLEMENTED` (2026-02-26)
- **Implementation:** CLI branches on `config.use_vertex_ai` to init client with `vertexai=True, project=..., location=...`. API key check skipped for Vertex AI. Mirrors existing logic in `session.py._get_client()`.
- **Files Modified:** `cli.py`
- **Tests:** 1 test in `test_cli.py`

### GAP-13: Video Metadata ffprobe Fallback
- **Status:** `IMPLEMENTED` (2026-02-26)
- **Implementation:** `_extract_video_metadata_ffprobe()` runs ffprobe subprocess with JSON output, parses duration/bitrate/codec/dimensions. Called when mutagen fails or returns empty. Guarded by `shutil.which()` and 10-second timeout.
- **Files Modified:** `metadata.py`
- **Tests:** 3 tests in `test_metadata.py`

### GAP-14: Single-File Folder Optimization
- **Status:** `IMPLEMENTED` (2026-02-26)
- **Implementation:** `_name_single_file()` generates name algorithmically from `ContentSummary.primary_subject` when folder has exactly 1 processable file. Zero additional API calls. Downstream `validate_renames()` still sanitizes the result (handles Windows reserved names, max length, collisions).
- **Files Modified:** `namer.py`
- **Tests:** 4 tests in `test_namer.py`

### GAP-15: `__init__.py` Public API Exports
- **Status:** `IMPLEMENTED` (2026-02-26)
- **Implementation:** `__all__` expanded to 17 exports: session API, config, all data models, version.
- **Files Modified:** `__init__.py`

### GAP-16: Legacy Office Format Metadata Extractors
- **Status:** `IMPLEMENTED` (2026-02-26)
- **Implementation:** `_extract_legacy_office_metadata()` uses `olefile` (lazy import) to read OLE2 properties from DOC/PPT/XLS. `olefile>=0.46` added to `pyproject.toml` as `[legacy-office]` optional dependency and included in `[full]` extras.
- **Files Modified:** `metadata.py`, `pyproject.toml`
- **Tests:** 3 tests in `test_metadata.py`

---

## Already Implemented Correctly

- ✅ File discovery & 4-tier categorization (discovery.py)
- ✅ Symlink detection, reverse mapping, and post-rename updating (discovery.py, executor.py)
- ✅ Cross-platform name sanitization — all 19 rules from PRD §8 (validator.py)
- ✅ Collision resolution — internal + external (validator.py)
- ✅ 4-tier naming strategy pattern: Full/Clustered/Sampled/Progressive (namer.py)
- ✅ Atomic rename protocol with manifest tracking (executor.py, manifest.py)
- ✅ Cross-platform file locking: fcntl (POSIX) + msvcrt (Windows) (logger.py)
- ✅ Undo via reverse-order replay (executor.py)
- ✅ Configuration layering: CLI > env > YAML > defaults (config.py)
- ✅ JSONL history logging with atomic appends (logger.py)
- ✅ Metadata extraction: 13+ format-specific extractors with lazy imports (metadata.py)
- ✅ Format conversion: SVG→PNG, BMP→PNG, GIF→PNG, Office→PDF (preprocessing.py)
- ✅ Content analysis & holistic naming prompts with proper escaping (constants.py)
- ✅ Exponential backoff with jitter on API failures (analyzer.py)
- ✅ Gemini File Upload + PROCESSING state polling (analyzer.py)
- ✅ Gemini response_json_schema for structured output validation (analyzer.py, namer.py)
- ✅ All Pydantic v2 data models with proper validation (models.py)
- ✅ 313 passing tests across 12 test files (tests/)
- ✅ 49 real fixture files across 13 directories (tests/fixtures/)
- ✅ Locked file handling with skip-and-continue (executor.py)
- ✅ File modified during processing detection (analyzer.py)
- ✅ Network drive detection with user-visible warning (executor.py, models.py, cli.py)
- ✅ Single-file folder optimization (namer.py)
- ✅ Video metadata ffprobe fallback (metadata.py)
- ✅ Legacy Office format extractors via olefile (metadata.py)
- ✅ Vertex AI client initialization support (cli.py, session.py)
- ✅ Public API: 17 symbols exported in __all__ (__init__.py)

---
