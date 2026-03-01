# AI File Rename — Operations Manual

> Version 1.0.0 | CLI reference for humans and agents

---

## Table of Contents

1. [Installation & Setup](#installation--setup)
2. [Quick Start](#quick-start)
3. [Commands](#commands)
4. [Operating Modes](#operating-modes)
5. [CLI Reference](#cli-reference)
6. [Configuration](#configuration)
7. [Pipeline Architecture](#pipeline-architecture)
8. [Naming Strategies](#naming-strategies)
9. [Supported File Types](#supported-file-types)
10. [Safety & Recovery](#safety--recovery)
11. [Cost Management](#cost-management)
12. [Troubleshooting](#troubleshooting)

---

## Installation & Setup

### Install the package

```bash
pip install -e ".[full]"       # All optional dependencies
pip install -e ".[dev]"        # Development dependencies
```

### Optional dependency groups

| Group          | What it enables                              | Packages                                   |
|----------------|----------------------------------------------|---------------------------------------------|
| `images`       | Image EXIF extraction                        | Pillow                                      |
| `pdf`          | PDF metadata extraction                      | PyPDF2                                      |
| `office`       | DOCX/PPTX/XLSX metadata                      | python-docx, python-pptx, openpyxl          |
| `legacy-office`| .doc/.ppt/.xls support                       | olefile                                     |
| `audio`        | Audio metadata (MP3, FLAC, etc.)             | mutagen                                     |
| `geo`          | Reverse geocoding from GPS EXIF              | reverse_geocoder                            |
| `svg`          | SVG-to-PNG conversion                        | cairosvg                                    |
| `full`         | All of the above                             | (all)                                       |

### Set your API key

```bash
# Option A: environment variable (recommended)
export GEMINI_API_KEY="your-key-here"

# Option B: config file
echo "gemini_api_key: your-key-here" > ~/.ai-rename.yaml

# Option C: .env file in project root
echo "GEMINI_API_KEY=your-key-here" > .env
```

### External tools (optional)

- **LibreOffice** — required for DOCX/PPTX/XLSX to PDF conversion (`--skip-converted` to bypass)
- **ffprobe** (part of FFmpeg) — fallback for video metadata when mutagen can't parse a format

---

## Quick Start

```bash
# Dry-run (default): see what would be renamed, no files touched
ai-rename rename ~/Downloads

# Recursive dry-run
ai-rename rename ~/Documents -r

# Execute renames after reviewing the dry-run table
ai-rename rename ~/photos -r -x

# Fully automated (no prompts, plain output)
ai-rename rename ~/archive -r -x -H -P

# Undo the last rename operation
ai-rename undo ~/Downloads
```

---

## Commands

### `ai-rename rename <target_directory> [OPTIONS]`

The primary command. Scans the target directory, analyzes file contents with Gemini, and proposes descriptive names.

**Arguments:**

| Argument           | Required | Description                    |
|--------------------|----------|--------------------------------|
| `target_directory` | Yes      | Path to the directory to scan  |

### `ai-rename undo [target_directory] [OPTIONS]`

Reverses the last rename operation in a directory using the stored manifest.

**Arguments:**

| Argument           | Required | Default | Description                          |
|--------------------|----------|---------|--------------------------------------|
| `target_directory` | No       | `.`     | Directory where renames were applied |

**Flags:**

| Flag       | Short | Description                    |
|------------|-------|--------------------------------|
| `--force`  | `-f`  | Skip the confirmation prompt   |

### `ai-rename history [OPTIONS]`

View past rename sessions from the global log.

**Options:**

| Option        | Short | Type | Default | Description                      |
|---------------|-------|------|---------|----------------------------------|
| `--directory` | `-d`  | path | None    | Filter history by directory      |
| `--last`      | `-n`  | int  | 10      | Show the last N sessions         |
| `--json`      |       | flag | False   | Output as JSON instead of text   |

---

## Operating Modes

The tool has two distinct modes designed for different use cases.

### Interactive Mode (DUI-Heavy)

**When:** Default behavior — no special flags needed.

Best for manual, careful operations where you want to review every proposed rename before committing.

```bash
ai-rename rename ~/photos -r
```

**Flow:**

1. Discover files and display an impact assessment panel
2. Prompt: *"Proceed with content analysis?"* → Yes/No
3. Analyze content and generate names (two Gemini API calls per folder)
4. Display a rich table of proposed renames (current → proposed)
5. Interactive review menu:
   - **`[A]` Approve all** — execute every rename
   - **`[R]` Reject all** — abort, no changes
   - **`[E]` Edit** — review each file individually (accept / reject / custom name)
   - **`[S]` Save & quit** — save the plan to `ai-rename-plan.json` for later
6. Execute approved renames atomically
7. Display execution summary

**Characteristics:**
- Rich terminal UI (colored tables, spinners, panels via Rich library)
- 4 confirmation prompts before any file is touched
- Per-file granular control with the Edit option
- Save-and-resume workflow

### Headless Mode (Agent-Light)

**When:** Pass `-H` (headless) and typically `-x` (execute). Add `-P` (plain) for machine-parseable output.

Best for automated pipelines, CI/CD, scripts, and agent consumption.

```bash
ai-rename rename ~/archive -r -x -H -P
```

**Flow:**

1. Discover files (no prompt)
2. Analyze content and generate names (no prompt)
3. Display proposed renames in plain text
4. Execute renames immediately (no prompt)
5. Print structured execution summary

**Characteristics:**
- No interactive prompts — fully autonomous
- Plain-text structured output (key: value format) for easy parsing
- No Rich formatting — safe for log files and pipes
- Machine-parseable status lines: `[PHASE]`, `[DONE]`, `[IMPACT ASSESSMENT]`, `[PROPOSED RENAMES]`, `[EXECUTION SUMMARY]`

### Mode Comparison

| Aspect               | Interactive (DUI-Heavy) | Headless (Agent-Light)     |
|-----------------------|-------------------------|----------------------------|
| User prompts          | 4 confirmation points   | None                       |
| Output format         | Rich panels & tables    | Structured plain text      |
| Dry-run table         | Colored Rich table      | Pipe-delimited text        |
| Final confirmation    | Interactive menu (A/R/E/S) | Auto-confirm            |
| Per-file editing      | Yes (Edit mode)         | No                         |
| Save plan to JSON     | Yes                     | No                         |
| Typical flags         | (none or `-r`)          | `-r -x -H -P`             |
| Use case              | Human reviewing files   | Scripts, agents, CI/CD     |

### Plain Output Mode (`--plain` / `-P`)

Can be used in either mode. Disables Rich formatting and outputs structured key-value pairs:

```
[IMPACT ASSESSMENT]
target_directory: /Users/me/photos
mode: recursive
total_files: 45
supported_files: 38
unsupported_files: 7
already_well_named: 3
folders_affected: 5
estimated_api_calls: 10
estimated_cost_usd: 0.02

[PHASE] Discovering files ...
[DONE]  Discovering files

[PROPOSED RENAMES] count=35
    1. [rename] IMG_001.jpg -> team-meeting-photo.jpg
    2. [rename] DSC_4521.jpg -> sunset-beach-panorama.jpg
    3. [unchanged] project-report.pdf -> project-report.pdf

[EXECUTION SUMMARY]
total_files: 35
files_renamed: 33
files_skipped: 2
files_failed: 0
duration_seconds: 12.4
tokens_used: 24,500
estimated_cost_usd: 0.0150
status: success
```

---

## CLI Reference

### `rename` Command — All Flags & Options

| Flag / Option            | Short | Type    | Default            | Description                                                |
|--------------------------|-------|---------|--------------------|------------------------------------------------------------|
| `--recursive`            | `-r`  | flag    | `False`            | Process subdirectories recursively                         |
| `--execute`              | `-x`  | flag    | `False`            | Execute renames (skip dry-run-only behavior)               |
| `--headless`             | `-H`  | flag    | `False`            | No interactive prompts; auto-confirm everything            |
| `--dry-run`              | `-d`  | flag    | `False`            | Explicit dry-run (default behavior, overrides `-x`)        |
| `--plain`                | `-P`  | flag    | `False`            | Plain text output — no Rich formatting                     |
| `--verbose`              | `-v`  | flag    | `False`            | Enable verbose logging to console                          |
| `--config`               | `-c`  | path    | `~/.ai-rename.yaml`| Path to a custom YAML config file                          |
| `--model`                | `-m`  | string  | `gemini-2.5-flash` | Gemini model to use                                        |
| `--max-files`            |       | int     | `500`              | Max files to process in a single run                       |
| `--custom-instructions`  | `-i`  | string  | None               | Extra naming instructions passed to Gemini                 |
| `--cost-limit`           |       | float   | `5.00`             | USD cost limit — warns if estimated cost exceeds this      |
| `--include`              |       | glob    | None               | Glob pattern for files to include (e.g., `"*.jpg"`)        |
| `--exclude`              |       | glob    | None               | Glob pattern for files to exclude (e.g., `"*.tmp"`)        |
| `--skip-converted`       |       | flag    | `False`            | Skip format conversion (DOCX→PDF, SVG→PNG, etc.)          |
| `--log-level`            |       | choice  | `INFO`             | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`             |
| `--no-skip-well-named`   |       | flag    | `False`            | Disable the well-named heuristic — analyze ALL files       |

### Flag Interactions

- `--dry-run` overrides `--execute` — if both are set, dry-run wins.
- `--dry-run` also overrides `--headless` execution — headless mode will analyze and display proposed renames but will NOT execute them.
- `--headless` disables Rich output and skips all interactive prompts.
- `--plain` can be used independently to get structured output even in interactive mode.

### Available Models

| Model               | Cost (input/output per 1M tokens) | Best for                        |
|----------------------|------------------------------------|---------------------------------|
| `gemini-2.0-flash`   | $0.10 / $0.40                     | Fastest, cheapest               |
| `gemini-2.5-flash`   | $0.15 / $0.60                     | Default — good balance          |
| `gemini-2.5-pro`     | $1.25 / $5.00                     | Most capable, higher cost       |

---

## Configuration

### Precedence (highest to lowest)

1. **CLI flags** — e.g., `--model gemini-2.5-pro`
2. **Environment variables** — e.g., `GEMINI_API_KEY`, `AI_RENAME_MAX_FILES`
3. **Config file** — `~/.ai-rename.yaml` (or path specified by `--config`)
4. **Built-in defaults** — Pydantic model defaults

### Environment Variables

All config fields can be set via environment variables with the `AI_RENAME_` prefix:

```bash
export GEMINI_API_KEY="..."            # Special: no prefix needed
export AI_RENAME_MODEL="gemini-2.5-pro"
export AI_RENAME_MAX_FILES="1000"
export AI_RENAME_COST_LIMIT="10.00"
export AI_RENAME_SEPARATOR="_"
export AI_RENAME_MAX_WORDS="10"
export AI_RENAME_LOG_LEVEL="DEBUG"
export AI_RENAME_SKIP_WELL_NAMED="false"
```

### YAML Config File

Default location: `~/.ai-rename.yaml`

```yaml
gemini_api_key: sk-xxx...
model: gemini-2.5-flash

naming:
  max_words: 8
  min_words: 2
  separator: "-"
  include_dates: true
  language: en

safety:
  max_files: 500
  cost_limit: 5.00
  require_confirmation: true

processing:
  concurrency: 3
  convert_office_docs: true
  skip_well_named: true

logging:
  log_level: INFO
  log_dir: ~/.ai-rename/logs

exclude_patterns:
  - ".*"
  - "*.tmp"
  - "node_modules"
  - "__pycache__"
  - ".git"
```

### All Configuration Fields

| Field                 | Type       | Default                     | Description                                           |
|-----------------------|------------|-----------------------------|-------------------------------------------------------|
| `gemini_api_key`      | string     | `""`                        | Gemini API key                                        |
| `use_vertex_ai`       | bool       | `false`                     | Use Vertex AI instead of direct API                   |
| `vertex_project`      | string     | None                        | GCP project ID (Vertex AI only)                       |
| `vertex_location`     | string     | None                        | GCP region (Vertex AI only)                           |
| `model`               | string     | `gemini-2.5-flash`          | Gemini model identifier                               |
| `max_words`           | int        | `8`                         | Max hyphen-separated words in generated name          |
| `min_words`           | int        | `2`                         | Min hyphen-separated words in generated name          |
| `separator`           | string     | `"-"`                       | Word separator in generated names                     |
| `include_dates`       | bool       | `true`                      | Include date references in names when relevant        |
| `language`            | string     | `en`                        | Primary language for naming                           |
| `custom_instructions` | string     | None                        | Extra instructions appended to the naming prompt      |
| `max_files`           | int        | `500`                       | Maximum files to process per run                      |
| `cost_limit`          | float      | `5.00`                      | USD cost warning threshold                            |
| `require_confirmation`| bool       | `true`                      | Require user confirmation (disabled by `--headless`)  |
| `concurrency`         | int        | `3`                         | Max concurrent API calls                              |
| `convert_office_docs` | bool       | `true`                      | Convert DOCX/PPTX/XLSX to PDF for analysis            |
| `skip_well_named`     | bool       | `true`                      | Skip files that already have descriptive names        |
| `log_level`           | string     | `INFO`                      | Logging level                                         |
| `log_dir`             | path       | `~/.ai-rename/logs`         | Directory for log files                               |
| `include_patterns`    | list[str]  | `[]`                        | Glob patterns for files to include                    |
| `exclude_patterns`    | list[str]  | `[".*", "*.tmp", ...]`      | Glob patterns for files to exclude                    |

---

## Pipeline Architecture

The rename pipeline runs in 8 sequential phases:

```
[1] Discovery          Scan filesystem, classify files, build symlink map
        ↓
[2] Impact Assessment  Display file counts, cost estimate, warnings
        ↓
[3] Preprocessing      Convert formats (SVG→PNG, DOCX→PDF) into temp dir
        ↓
[4] Metadata           Extract EXIF, document properties, audio tags, ffprobe
        ↓
[5] Context Building   Build folder hierarchy, breadcrumbs, sibling lists
        ↓
[6] Content Analysis   Gemini API call #1 — per-file content summary
        ↓
[7] Holistic Naming    Gemini API call #2 — per-folder cohesive naming
        ↓
[8] Validation         Sanitize names, resolve collisions, cross-platform checks
        ↓
[9] Execution          Atomic renames with manifest tracking + symlink updates
```

### Single-File Optimization

When a folder contains exactly **1 file**, the tool skips the holistic naming API call entirely (phase 7). Instead, it derives the name deterministically from the content analysis summary. This saves one API call per single-file folder.

**Important:** Even in single-file mode, the tool still processes:
- Full folder metadata (parent path, breadcrumbs, hierarchy)
- File metadata (EXIF, document properties, etc.)
- Content analysis via Gemini (the first API call still runs)
- All validation and safety checks

Only the *second* LLM call (holistic naming) is skipped — not the folder context.

### Metadata Extraction

The tool extracts rich metadata to inform naming:

| File Type  | Extractor   | Metadata Fields                                              |
|------------|-------------|--------------------------------------------------------------|
| Images     | Pillow/EXIF | dimensions, camera make/model, GPS, date taken               |
| PDF        | PyPDF2      | title, author, subject, page count, creation date            |
| DOCX       | python-docx | title, author, word count, page count                        |
| PPTX       | python-pptx | title, author, slide count                                   |
| XLSX       | openpyxl    | title, author, sheet names                                   |
| Audio      | mutagen     | artist, album, genre, duration, bitrate                      |
| Video      | mutagen     | duration, codec, bitrate (with ffprobe fallback)             |

#### ffprobe Fallback

For video files where mutagen cannot extract metadata (some MKV, FLV, or unusual codecs), the tool falls back to `ffprobe`:

```bash
ffprobe -v error -show_entries format=duration,bit_rate -of json file.mp4
```

- 5-second timeout to prevent blocking
- Graceful degradation: if ffprobe is not installed or fails, metadata is simply empty
- No error is raised — the pipeline continues with whatever metadata is available

---

## Naming Strategies

The tool selects a naming strategy based on the number of files in each folder:

| File Count | Strategy                 | Approach                                                  |
|------------|--------------------------|-----------------------------------------------------------|
| 1          | Single-File Optimization | Deterministic name from content summary (no LLM call)    |
| 2–50       | FullHolisticStrategy     | One LLM call names all files together                    |
| 51–200     | ClusteredHolisticStrategy| Cluster by content type, name each cluster separately    |
| 201–500    | SampledHolisticStrategy  | Sample 50 files, establish pattern, apply to rest         |
| 500+       | ProgressiveHolisticStrategy | Sequential batches of 50 with accumulated context      |

### Naming Rules

All generated names follow these cross-platform constraints:

- Lowercase only
- 2–8 hyphen-separated words (configurable)
- ASCII only (non-ASCII transliterated)
- No forbidden characters: `< > : " / \ | ? *`
- No Windows reserved names (CON, PRN, AUX, NUL, COM1–9, LPT1–9)
- Maximum 200 characters including extension
- Extension is never changed
- Each name is unique within its folder

### Well-Named Detection (Smart Skip)

Files that already have descriptive names are automatically skipped to save API calls and processing time. This is one of the tool's most cost-effective features — in a folder of 100 files where 30 are already well-named, you save ~30% on API costs.

A file is considered "well-named" when ALL of these are true:
- Stem is at least 15 characters long
- Contains 3+ semantically meaningful word tokens (excluding filler words like "file", "document", "the", "with")
- Does not match known auto-generated patterns (IMG_, DSC_, Screenshot, UUID, hex hash, timestamps)
- No version/draft indicators (`_v2`, `_FINAL`, `_draft`, `_copy`)
- No repeated words (case-insensitive — catches `report_final_FINAL`)
- No excessive ALL_CAPS tokens (suggests sloppy/automated naming)

**Examples:**

| Filename | Well-Named? | Why |
|----------|-------------|-----|
| `quarterly-revenue-report-2023.pdf` | Yes | Descriptive, specific, clean |
| `meeting-notes-project-alpha.txt` | Yes | Descriptive, specific |
| `IMG_20190412_143022.jpg` | No | Camera auto-generated |
| `presentation_final_v2_FINAL.pptx` | No | Version indicator, repeated word |
| `document(1).pdf` | No | Too short, numbered duplicate |
| `file_with_bad_chars.txt` | No | Generic filler word "file" |

**To bypass:** Use `--no-skip-well-named` to force analysis of ALL files:
```bash
ai-rename rename ~/docs --no-skip-well-named
```

Or set `skip_well_named: false` in `~/.ai-rename.yaml`.

---

## Supported File Types

### Tier 1: Directly Processable (Native Gemini)

Uploaded directly to Gemini for analysis.

**Images:** JPEG, JPG, PNG, WEBP, HEIC, HEIF
**Documents:** PDF
**Audio:** MP3, WAV, AAC, OGG, FLAC, AIFF
**Video:** MP4, MOV, AVI, WEBM, WMV, MKV, FLV

### Tier 2: Convertible (Pre-processing required)

Converted to a Gemini-native format before upload.

| Source Format        | Converted To | Converter       |
|----------------------|--------------|-----------------|
| SVG                  | PNG          | cairosvg        |
| GIF, BMP, TIFF, TIF | PNG          | Pillow          |
| DOCX, PPTX, XLSX    | PDF          | LibreOffice     |
| DOC, PPT, XLS       | PDF          | LibreOffice     |

### Tier 3: Text-Extractable

Read as text content (up to 50KB) and sent as text to Gemini.

TXT, MD, HTML, XML, JSON, YAML, CSV, TSV, PY, JS, TS, RS, GO, JAVA, C, CPP, H, HPP, RB, PHP, SH, BASH, ZSH, LOG, INI, TOML, CFG, CONF, ENV, SQL, R, SWIFT, KT, SCALA, LUA, PL, PM

### Tier 4: Unsupported (Skipped)

ZIP, TAR, GZ, RAR, 7Z, EXE, APP, DMG, MSI, DEB, RPM, ISO, IMG, DB, SQLITE, MDB, DLL, SO, DYLIB, SYS, PSD, AI, SKETCH, FIG, TTF, OTF, WOFF, WOFF2, OBJ, STL, FBX, BLEND

---

## Safety & Recovery

### Dry-Run by Default

The tool defaults to dry-run mode. No files are renamed unless you pass `--execute` or approve in the interactive menu.

### Manifest-Based Recovery

During execution, an ephemeral manifest file (`.ai-rename-manifest.json`) is written to the target directory:

- Records each rename's status (`pending` → `completed`)
- Enables crash recovery — if the process is interrupted, the next run detects the manifest and offers: **resume**, **undo**, or **discard**
- Automatically cleaned up on successful completion

### Undo

```bash
ai-rename undo ~/photos        # Interactive confirmation
ai-rename undo ~/photos -f     # Skip confirmation
```

Reverses ALL renames from the last session by reading the manifest.

### Symlink Safety

- Incoming symlinks are detected during discovery
- When a file is renamed, all symlinks pointing to it are updated
- Relative vs. absolute symlink style is preserved
- Atomic `os.symlink()` + `os.replace()` pattern

### Atomic Rename Protocol

Each file rename follows this sequence:

1. Record intent in manifest (status: `pending`)
2. Execute `os.rename()`
3. Verify: old path gone, new path exists, file size unchanged
4. Update any incoming symlinks
5. Record success (status: `completed`)
6. On ANY failure: stop immediately, preserve manifest for recovery

### Run Reports (Live Status File)

Every run produces a **stateful report file** in the target directory that is updated progressively as the pipeline advances:

```
.ai-rename-report-{run_id}.md
```

Example: `.ai-rename-report-20260301-501df6ed.md`

**How it works:**
- The file is created at the start of the run with a fixed timestamp
- It is rewritten at each phase transition with accumulated data
- The **Status** field shows the current pipeline phase in real time
- The final state of this file IS the complete run report

**Phase progression visible in the Status field:**

| Status | What it means |
|--------|---------------|
| `starting` | Run initialized, about to discover files |
| `discovered` | File discovery complete, impact summary available |
| `analyzing` | Content analysis in progress with Gemini |
| `proposed` | Names generated — rename table available |
| `completed` | Renames executed successfully |
| `dry-run-complete` | Dry-run finished — no files were modified |

**Report contents (cumulative — each phase adds data):**
- Run metadata: run ID, start timestamp, model, target, recursive flag
- Current status and mode (dry-run vs executed)
- Impact summary: files found, supported, unsupported, well-named skipped
- Token usage and estimated cost
- Markdown table of all proposed renames (current name / proposed name / notes)
- Skipped well-named files list
- Analysis failures list
- Execution results (renamed/skipped/failed counts) — only after execution

**For humans watching a long-running job:**
```bash
# Watch the report file update in real time
watch -n 2 cat ~/photos/.ai-rename-report-20260301-*.md
```

**For AI agents running headlessly:**
The report file is the single source of truth for what happened in a run. After invoking `ai-rename rename <dir> -r -x -H -P`, read the `.ai-rename-report-*.md` file in the target directory to get:
- Whether the run succeeded (Status = `completed`) or is still running
- The full rename table (what was renamed and to what)
- Any analysis failures or warnings
- Token/cost accounting

This is more structured and reliable than parsing CLI stdout.

Reports are timestamped with the run ID so multiple runs never overwrite each other. They are listed in `.gitignore` by default.

---

## Cost Management

### Estimating Costs

The tool estimates costs before any API calls and displays them in the impact assessment:

```
Est. API calls:   ~10
Est. cost:        ~$0.02
```

### Cost Limit

Set a cost ceiling with `--cost-limit` (default: $5.00 USD):

```bash
ai-rename rename ~/files --cost-limit 2.00
```

If the estimated cost exceeds the limit, the tool warns and asks for confirmation (or aborts in headless mode).

### Minimizing Costs

1. **Use `gemini-2.0-flash`** for the cheapest option: `--model gemini-2.0-flash`
2. **Skip well-named files** (enabled by default): files with descriptive names are not analyzed
3. **Use `--include` to target specific file types**: `--include "*.jpg"`
4. **Single-file optimization** automatically saves one API call per single-file folder
5. **Always dry-run first** to see the impact assessment before committing

### API Limits

| Limit                    | Value      |
|--------------------------|------------|
| Max single file size     | 2 GB       |
| Max request payload      | 100 MB     |
| Max batch size            | 80 MB      |
| Max PDF pages            | 1,000      |
| Max retries (per call)   | 5          |
| Retry backoff (base)     | 1 second   |

---

## Troubleshooting

### Common Issues

**"No API key found"**
```bash
export GEMINI_API_KEY="your-key"
# or add to ~/.ai-rename.yaml
```

**"google-genai package not installed"**
```bash
pip install google-genai
```

**Office documents not converting**
- Install LibreOffice: `brew install --cask libreoffice` (macOS)
- Or use `--skip-converted` to skip conversion

**Video metadata missing**
- Install FFmpeg for ffprobe: `brew install ffmpeg` (macOS)
- Metadata is optional — the pipeline continues without it

**"Estimated cost exceeds limit"**
- Increase the limit: `--cost-limit 10.00`
- Or use a cheaper model: `--model gemini-2.0-flash`
- Or narrow the scope: `--include "*.jpg"` or remove `-r`

### Logs

All sessions are logged to `~/.ai-rename/logs/`:
- Per-session log files with timestamps
- Global history JSON for `ai-rename history`
- CSV session ledger with token/cost tracking

### Interrupted Runs

If a run is interrupted mid-rename, the next run in the same directory detects the manifest and offers:

- **Resume** — continue pending renames
- **Undo** — reverse completed renames
- **Discard** — delete the manifest and start fresh

---

## Examples

### Human Workflows

```bash
# Sort a messy Downloads folder
ai-rename rename ~/Downloads -r

# Rename photos with date context
ai-rename rename ~/Photos/2024-vacation -i "Include location and date in names"

# Process only images
ai-rename rename ~/Desktop --include "*.{jpg,png,heic}"

# Use the most capable model for important documents
ai-rename rename ~/Documents/contracts -m gemini-2.5-pro
```

### Agent / Script Workflows

```bash
# Fully automated: rename and move on
ai-rename rename /data/incoming -r -x -H -P

# Dry-run check with parseable output
ai-rename rename /data/staging -r -P -d 2>/dev/null

# Cost-capped batch processing
ai-rename rename /archive/2023 -r -x -H -P --cost-limit 2.00 --model gemini-2.0-flash

# Check history programmatically
ai-rename history --json -n 5
```

### Custom Instructions

```bash
# Prioritize brevity
ai-rename rename ~/docs -i "Keep names as short as possible, 2-3 words max"

# Include author names
ai-rename rename ~/papers -i "Always include the first author's surname"

# Domain-specific naming
ai-rename rename ~/medical-images -i "Use anatomical terminology when describing body parts"
```
