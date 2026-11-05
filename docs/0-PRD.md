# Product Requirements Document: AI File Rename Tool

**Version:** 1.0.0
**Date:** 2026-02-25
**Author:** Auto-generated from stakeholder interview
**Status:** Draft: Awaiting Review

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Goals & Non-Goals](#3-goals--non-goals)
4. [User Personas & Use Cases](#4-user-personas--use-cases)
5. [System Architecture](#5-system-architecture)
6. [Core Workflow](#6-core-workflow)
7. [File Processing Pipeline](#7-file-processing-pipeline)
8. [Naming Strategy & Conventions](#8-naming-strategy--conventions)
9. [Holistic Naming Engine](#9-holistic-naming-engine)
10. [Safety & Failsafe Mechanisms](#10-safety--failsafe-mechanisms)
11. [State Management](#11-state-management)
12. [CLI Interface Design](#12-cli-interface-design)
13. [Gemini SDK Integration](#13-gemini-sdk-integration)
14. [File Metadata Enrichment](#14-file-metadata-enrichment)
15. [Supported File Types & Processing Strategies](#15-supported-file-types--processing-strategies)
16. [Scalability & Batching Strategy](#16-scalability--batching-strategy)
17. [Configuration & Customization](#17-configuration--customization)
18. [Logging & Observability](#18-logging--observability)
19. [Error Handling & Edge Cases](#19-error-handling--edge-cases)
20. [Cross-Platform Compatibility](#20-cross-platform-compatibility)
21. [Security Considerations](#21-security-considerations)
22. [Testing Strategy](#22-testing-strategy)
23. [Tech Stack & Dependencies](#23-tech-stack--dependencies)
24. [Future Considerations](#24-future-considerations)
25. [Appendix](#25-appendix)

---

## 1. Executive Summary

**ai-file-rename** is a lightweight, deterministic CLI tool (and Python library) that uses Google's Gemini AI to intelligently rename files based on their actual content, contextual placement within a folder hierarchy, and relationship to sibling files. It transforms cryptic, default-download file names into semantically rich, descriptive names that enable both humans and AI agents to instantly understand a file's purpose without opening it.

The tool is designed for a specific personal use case: making 15+ years of accumulated digital files, scattered across deep folder hierarchies with meaningless names, discoverable and useful again. The design philosophy is **deterministic over agentic**: a structured pipeline with predefined rules, not an autonomous agent making decisions.

### Design Principles

1. **Deterministic, not agentic.** The tool follows a fixed pipeline. No autonomous decision-making loops, no self-modifying behavior. The LLM is used as a function (content in, name out), not as a planner.
2. **Safe by default.** Dry-run first. Atomic renames. Manifest-tracked state. Undo capability. No file is ever at risk.
3. **Context-rich.** A file's name is not determined in isolation. The folder hierarchy, sibling files, and content all contribute to producing a name that is maximally informative within its context.
4. **Lightweight.** Minimal dependencies. No database. No server. Runs from a terminal. Installable via pip.
5. **Cross-platform.** File names must be valid on Windows, macOS, and Linux simultaneously.

---

## 2. Problem Statement

### The Pain

A user has accumulated 15+ years of digital files across a personal hard drive. These files suffer from several naming problems:

| Problem | Example | Impact |
|---------|---------|--------|
| Default download names | `IMG_20190412_143022.jpg` | Zero context about content |
| Random hash names | `a7f3b2c1d4e5.pdf` | Completely opaque |
| Partial context names | `presentation_final_v2_FINAL.pptx` | Misleading, no content signal |
| Duplicate generic names | `document.pdf`, `document(1).pdf` | No differentiation |
| Deep nesting hides files | `~/archives/2019/misc/old/stuff/file.png` | Files are effectively lost |

### The Consequence

When an AI agent (or the user themselves) runs `ls` in any folder, they see a wall of meaningless names. The files are effectively invisible: present on disk but inaccessible to any workflow that relies on file names for navigation or context. In the era of AI-assisted workflows, where agents scan directories to understand available resources, **file names ARE the interface**.

### Why Now

Until recently, the only solution was manual renaming: opening each file, understanding its content, and choosing a descriptive name. For 10,000+ files, this is impractical. LLMs with multimodal capabilities (specifically Google Gemini) can now read images, PDFs, documents, audio, and video and produce contextual descriptions: enabling automated, intelligent renaming at scale.

### Why Gemini Specifically

Multiple LLM providers offer multimodal support, but Google's Gemini (via the `google-genai` SDK) provides the most comprehensive file processing pipeline:

- **Native PDF vision**: full visual understanding of charts, diagrams, tables, and layouts (not just text extraction).
- **File Upload API**: upload files up to 2 GB, retained for 48 hours, free to use.
- **Broad format support**: images, audio, video, and documents in a unified API.
- **Unified SDK**: the `google-genai` package works with both Google AI Studio (API key) and Vertex AI (service account), so the user is never locked in.

---

## 3. Goals & Non-Goals

### Goals

| ID | Goal | Success Metric |
|----|------|----------------|
| G1 | Rename files to reflect their actual content | A human or AI agent can understand a file's purpose from its name alone |
| G2 | Preserve file safety at all times | Zero file loss or corruption across all operations |
| G3 | Generate contextually differentiated names | Within a folder of 10 files, all 10 names are distinct and complementary |
| G4 | Work across all major OS platforms | Generated names are valid on Windows, macOS, and Linux |
| G5 | Provide full operational transparency | User sees exactly what will happen before it happens |
| G6 | Support undo and recovery | Any rename operation can be fully reversed |
| G7 | Handle large file collections efficiently | Process folders with 500+ files without degraded naming quality |
| G8 | Be installable and runnable with minimal setup | `pip install` + API key = ready to go |

### Non-Goals

| ID | Non-Goal | Rationale |
|----|----------|-----------|
| NG1 | Organizing files into folders | This tool renames, not reorganizes. Folder structure is preserved as-is. |
| NG2 | Deduplication | Detecting and removing duplicate files is a separate concern. |
| NG3 | Full-disk recursive operation | The tool operates on a user-specified directory, not the entire drive. |
| NG4 | Real-time / watch mode | No file system watchers. The tool runs on demand. |
| NG5 | GUI interface | CLI only. A GUI could be built on top of the library later. |
| NG6 | Content modification | Files are never opened for writing, only reading. Only the name changes. |
| NG7 | Cloud sync awareness | The tool does not know or care about Dropbox, iCloud, etc. |

---

## 4. User Personas & Use Cases

### Primary Persona: Digital Archivist

- **Who:** A power user with years of accumulated files across a personal hard drive.
- **Pain:** Cannot find files because names are meaningless. Folder structures provide some context but file names within folders are chaotic.
- **Goal:** Make every file self-describing so that both the user and AI tools can efficiently navigate the archive.
- **Technical comfort:** Comfortable with terminal, Python, API keys. Not necessarily a developer.

### Use Cases

**UC1: Single Folder Cleanup**
> "I have a folder `~/projects/2020-redesign/assets/` with 30 images named `IMG_*.jpg` and `Screenshot*.png`. I want each file renamed to describe what it actually depicts."

**UC2: Nested Folder Sweep**
> "I want to process `~/documents/research/` and all its subfolders. There are about 200 PDFs and Word documents with generic names. Rename them based on their actual content."

**UC3: Mixed Media Folder**
> "My `~/archive/conference-2022/` folder has presentation slides, photos, audio recordings, and handout PDFs. Rename everything so I can tell at a glance what each file is."

**UC4: Dry-Run Inspection**
> "Before committing to any renames, I want to see a table showing current name -> proposed name for every file, along with a confidence score. I'll review and approve."

**UC5: Undo After Regret**
> "I renamed 50 files but realized the naming pattern isn't what I wanted. I want to undo the entire batch and try again with different instructions."

**UC6: Headless / Scripted Operation**
> "I want to script this tool to run across 10 folders overnight. It should auto-confirm renames and log everything for my review in the morning."

---

## 5. System Architecture

### High-Level Architecture

```
+------------------------------------------------------------------+
|                         CLI ENTRYPOINT                            |
|  ai-rename <target-dir> [options]                                |
+------------------------------------------------------------------+
         |
         v
+------------------------------------------------------------------+
|                      DISCOVERY PHASE                              |
|  1. Walk target directory (+ optional subdirectories)             |
|  2. Inventory all files by type                                   |
|  3. Filter: supported vs unsupported formats                     |
|  4. Collect folder-level context (path hierarchy, sibling names)  |
|  5. Generate impact summary for user confirmation                 |
+------------------------------------------------------------------+
         |
         v
+------------------------------------------------------------------+
|                     PRE-PROCESSING PHASE                          |
|  1. Convert unsupported-but-convertible formats                   |
|     (SVG -> PNG, DOCX/PPTX/XLSX -> PDF)                         |
|  2. Group files by parent folder (naming context units)           |
|  3. Determine batching strategy per folder                        |
+------------------------------------------------------------------+
         |
         v
+------------------------------------------------------------------+
|                     CONTENT ANALYSIS PHASE                        |
|  Per folder (as a naming context unit):                           |
|  1. Upload each file to Gemini File API                           |
|  2. Send file + context prompt to Gemini model                    |
|  3. Receive per-file content summary (structured JSON)            |
|  4. Cache/store content summaries                                 |
+------------------------------------------------------------------+
         |
         v
+------------------------------------------------------------------+
|                   HOLISTIC NAMING PHASE                           |
|  Per folder:                                                      |
|  1. Collect all content summaries for files in this folder        |
|  2. Include folder hierarchy context                              |
|  3. Send holistic naming prompt to Gemini                         |
|  4. Receive mapping: {old_name -> proposed_name} for all files    |
|  5. Validate all proposed names against naming rules              |
|  6. Resolve any collisions                                        |
+------------------------------------------------------------------+
         |
         v
+------------------------------------------------------------------+
|                      DRY-RUN PRESENTATION                         |
|  1. Display table: current name | proposed name | confidence      |
|  2. Show impact summary (N files, M folders, estimated changes)   |
|  3. Await user confirmation (interactive) or auto-proceed          |
|     (headless mode)                                               |
+------------------------------------------------------------------+
         |
         v
+------------------------------------------------------------------+
|                      EXECUTION PHASE                              |
|  Per file (atomic operations):                                    |
|  1. Write rename intent to manifest (working JSON)                |
|  2. Execute os.rename() with safety checks                        |
|  3. Verify rename succeeded (confirm new path exists,             |
|     old path gone, file size unchanged)                           |
|  4. Update manifest with completion status                        |
|  5. On failure: halt, report, preserve manifest for recovery      |
+------------------------------------------------------------------+
         |
         v
+------------------------------------------------------------------+
|                      CLEANUP PHASE                                |
|  1. Write permanent log entry to global log file                  |
|  2. Remove ephemeral working manifest (on success)                |
|  3. Print summary report                                          |
+------------------------------------------------------------------+
```

### Component Diagram

```
ai-file-rename/
├── src/
│   └── ai_file_rename/
│       ├── __init__.py              # Package exports
│       ├── cli.py                   # CLI entrypoint (argparse/click)
│       ├── discovery.py             # File system scanning & inventory
│       ├── preprocessing.py         # Format conversion (SVG->PNG, DOCX->PDF)
│       ├── context.py               # Folder hierarchy & sibling context builder
│       ├── analyzer.py              # Gemini content analysis (per-file)
│       ├── namer.py                 # Holistic naming engine (per-folder batch)
│       ├── validator.py             # Name validation & collision resolution
│       ├── executor.py              # Safe atomic rename operations
│       ├── manifest.py              # Working manifest (ephemeral JSON state)
│       ├── logger.py                # Global persistent logging
│       ├── config.py                # Configuration management
│       ├── models.py                # Data models / typed dicts
│       └── constants.py             # Naming rules, format maps, limits
├── docs/
│   └── PRD.md                       # This document
├── tests/
├── pyproject.toml
└── README.md
```

---

## 6. Core Workflow

### Step-by-Step Execution Flow

#### Step 1: Invocation

```bash
ai-rename ~/documents/research/ --recursive --dry-run
```

The user specifies a target directory. The tool does NOT operate at the hard-drive root level. It operates on a specific directory, optionally including subdirectories.

#### Step 2: Discovery & Impact Assessment

The tool scans the target directory and produces an impact summary BEFORE doing any work:

```
╔══════════════════════════════════════════════════════════╗
║                    IMPACT ASSESSMENT                     ║
╠══════════════════════════════════════════════════════════╣
║  Target:      ~/documents/research/                      ║
║  Mode:        Recursive                                  ║
║                                                          ║
║  Files found:         247                                ║
║  ├── Supported:       231 (will be processed)            ║
║  └── Unsupported:      12 (will be skipped)              ║
║                                                          ║
║  Folders affected:     14                                ║
║  Deepest nesting:       4 levels                         ║
║                                                          ║
║  Estimated API calls:  ~48 (batched)                     ║
║  Estimated cost:       ~$0.35                            ║
║                                                          ║
║  File type breakdown:                                    ║
║  ├── PDF:        89  ████████████████░░░░░░  38%         ║
║  ├── JPEG:       67  ████████████░░░░░░░░░░  29%         ║
║  ├── PNG:        34  ██████░░░░░░░░░░░░░░░░  15%         ║
║  ├── DOCX:       22  ████░░░░░░░░░░░░░░░░░░   9%        ║
║  ├── PPTX:       11  ██░░░░░░░░░░░░░░░░░░░░   5%        ║
║  ├── MP3:         8  █░░░░░░░░░░░░░░░░░░░░░   3%        ║
║  └── Other:      16  ███░░░░░░░░░░░░░░░░░░░   7%        ║
╚══════════════════════════════════════════════════════════╝

Proceed with content analysis? [Y/n]:
```

This step is MANDATORY in interactive mode. The user must explicitly confirm before any API calls or file operations occur.

#### Step 3: Content Analysis (Per-File)

For each supported file, the tool:

1. Determines the processing strategy based on file type (see Section 14).
2. If conversion is needed (e.g., DOCX -> PDF), performs conversion to a temp directory.
3. Uploads the file (or its converted form) to the Gemini File API.
4. Sends a structured prompt asking for a content summary.
5. Receives and stores a structured JSON response.

**Per-file content analysis prompt structure:**

```
You are a file content analyzer. Your job is to produce a brief,
factual summary of this file's content that will be used to generate
a descriptive filename.

Context:
- This file is located at: {full_path}
- Parent folder: {parent_folder_name}
- Folder hierarchy: {breadcrumb_path}
- Current filename: {current_filename}
- File type: {mime_type}
- File size: {file_size_human_readable}
- Created date: {created_date}  (file system birth time)
- Last modified: {modified_date}  (file system mtime)
- Last accessed: {accessed_date}  (file system atime)
- Is symlink: {is_symlink} (target: {symlink_target} if applicable)
- Embedded metadata: {embedded_metadata_json}
  (May include: author, title, subject, camera model, GPS coordinates,
   document creator, page count, duration, dimensions, bitrate, etc.
   depending on file type. "null" if no embedded metadata was extracted.)

Instructions:
- Describe the PRIMARY content/subject of this file in 2-3 sentences.
- Identify the TYPE of content (e.g., "photograph of...",
  "presentation about...", "invoice from...", "research paper on...").
- Extract any key identifiers: dates, names, organizations, topics.
- Use the embedded metadata to enrich your understanding. For example:
  an author name, a document title, a camera location, or a creation
  date can all provide important context for naming.
- The file system dates and size are supplementary signals. A very
  large file may contain more substantial content. Creation dates
  may indicate when the content is from (though they can also reflect
  when the file was copied). Use these as hints, not as primary naming
  sources.
- Do NOT suggest a filename. Just describe the content.

Respond in this exact JSON format:
{
  "content_type": "photograph | document | presentation | spreadsheet | audio | video | diagram | screenshot | ...",
  "primary_subject": "brief description of the main subject",
  "key_entities": ["entity1", "entity2"],
  "date_references": ["YYYY-MM-DD or partial dates found in content OR metadata"],
  "language": "en | es | fr | ...",
  "confidence": 0.0-1.0
}
```

#### Step 4: Holistic Naming (Per-Folder)

After all files in a folder have been analyzed, the tool sends a SINGLE holistic naming request for the entire folder. This is the critical step that ensures names are contextually differentiated.

See [Section 9: Holistic Naming Engine](#9-holistic-naming-engine) for full details.

#### Step 5: Dry-Run Presentation

```
╔═══════════════════════════════════════════════════════════════════════╗
║  PROPOSED RENAMES: ~/documents/research/ml-papers/                  ║
╠═══════════════════════════════════════════════════════════════════════╣
║  #  │ Current Name              │ Proposed Name                      ║
║  ───┼───────────────────────────┼──────────────────────────────────── ║
║   1 │ paper_v2_final.pdf        │ attention-is-all-you-need-2017.pdf ║
║   2 │ download(3).pdf           │ bert-pretraining-devlin-2018.pdf   ║
║   3 │ arxiv-2301.12345.pdf      │ gpt4-technical-report-2023.pdf    ║
║   4 │ IMG_20230915_142233.jpg   │ conference-poster-nlp-workshop.jpg ║
║   5 │ notes.docx                │ reading-notes-transformer-arch.pdf ║
║  ───┼───────────────────────────┼──────────────────────────────────── ║
║  Confidence: HIGH (avg 0.91)                                         ║
╚═══════════════════════════════════════════════════════════════════════╝

[A]pprove all  |  [R]eject all  |  [E]dit individually  |  [S]ave & quit
```

#### Step 6: Execution

See [Section 10: Safety & Failsafe Mechanisms](#10-safety--failsafe-mechanisms).

#### Step 7: Cleanup & Reporting

After successful execution:
- Permanent log entry written to global log.
- Ephemeral working manifest deleted.
- Summary printed to terminal.

---

## 7. File Processing Pipeline

### Pipeline Stages Per File

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐    ┌──────────┐
│ DISCOVER │───>│ CLASSIFY │───>│ CONVERT  │───>│ UPLOAD  │───>│ ANALYZE  │
│          │    │          │    │ (if req) │    │ (Gemini)│    │ (Gemini) │
└─────────┘    └──────────┘    └──────────┘    └─────────┘    └──────────┘
                                                                    │
                    ┌──────────┐    ┌──────────┐    ┌──────────┐    │
                    │  RENAME  │<───│ VALIDATE │<───│  NAME    │<───┘
                    │ (atomic) │    │          │    │(holistic)│
                    └──────────┘    └──────────┘    └──────────┘
```

### File Classification Matrix

Every file encountered is classified into one of four categories:

| Category | Action | Examples |
|----------|--------|---------|
| **Directly Processable** | Upload to Gemini as-is | JPEG, PNG, WebP, HEIC, PDF, MP3, WAV, MP4, MOV |
| **Convertible** | Convert to a processable format first | SVG (->PNG), GIF (->PNG first frame), DOCX (->PDF), PPTX (->PDF), XLSX (->PDF) |
| **Text-Extractable** | Read file content as text, send as text prompt | TXT, MD, HTML, XML, JSON, YAML, CSV, source code |
| **Unsupported** | Skip with warning | Binary executables, archives (ZIP, TAR), database files, proprietary formats |

---

## 8. Naming Strategy & Conventions

### Cross-Platform Naming Rules

All generated file names MUST comply with these rules to be valid on Windows, macOS, and Linux simultaneously:

| Rule | Constraint | Rationale |
|------|-----------|-----------|
| **Max length** | 200 characters (including extension) | Windows MAX_PATH is 260; leave room for path. Practical limit keeps names readable. |
| **Forbidden characters** | `< > : " / \ | ? *` | Windows forbids these. macOS/Linux forbid `/`. Union set is safest. |
| **No trailing dots or spaces** | Strip from end of name | Windows silently removes these, causing cross-platform inconsistency. |
| **No reserved names** | Avoid `CON, PRN, AUX, NUL, COM1-9, LPT1-9` | Windows reserves these regardless of extension. |
| **Lowercase only** | Force all names to lowercase | Prevents case-sensitivity issues between macOS (case-insensitive by default) and Linux (case-sensitive). |
| **Word separator** | Hyphens (`-`) only | Consistent, URL-safe, readable. No spaces, underscores, or camelCase. |
| **No leading dots** | Prefix with `_` if name would start with `.` | Prevents files from becoming hidden on Unix systems. |
| **Extension preserved** | Original extension is NEVER changed | The tool renames the stem only. `.pdf` stays `.pdf`. |
| **ASCII only** | Transliterate non-ASCII to closest ASCII equivalent | Prevents encoding issues across systems. `café` -> `cafe`, `über` -> `uber`. |

### Naming Format

The generated file name follows this pattern:

```
{descriptive-content-slug}.{original-extension}
```

Where `{descriptive-content-slug}` is:
- **2-8 hyphen-separated words** that describe the file's content.
- Words are ordered by **specificity**: most specific/unique descriptor first, most general last.
- If a meaningful date is part of the content (not the file metadata), it MAY be appended: `quarterly-revenue-report-2023-q3.xlsx`.
- Names should be **noun-phrase** oriented, not sentences: `sunset-over-golden-gate-bridge.jpg` not `this-is-a-photo-of-sunset.jpg`.

### Naming Quality Criteria

The Gemini naming prompt includes these quality criteria:

1. **Specificity:** The name should distinguish this file from its siblings. "report.pdf" is bad. "annual-security-audit-2023.pdf" is good.
2. **Accuracy:** The name must truthfully reflect the content. No hallucinated context.
3. **Brevity:** Shorter is better, but not at the cost of specificity. Target 3-6 words.
4. **Consistency:** Within a folder, names should follow a consistent pattern. If one file is `invoice-january-2023.pdf`, its sibling should be `invoice-february-2023.pdf`, not `feb-billing-statement.pdf`.
5. **Complementarity:** Names within a folder should collectively tell a story. Each name occupies a distinct semantic niche.

---

## 9. Holistic Naming Engine

This is the most critical component of the system. Files within a folder are NOT named independently: they are named as a cohort, with full awareness of each other.

### Why Holistic Naming Matters

Consider a folder `~/photos/vacation-2023/` containing 15 photos. If each photo were named independently, you might get:

```
beach-scene.jpg
beach-scene.jpg          # COLLISION!
beach-sunset.jpg
beach-with-people.jpg
ocean-view.jpg           # Too similar to beach-scene
```

With holistic naming, the same folder produces:

```
arrival-day-hotel-lobby.jpg
beachfront-morning-walk.jpg
cliff-diving-at-sunset.jpg
dinner-at-seaside-restaurant.jpg
group-photo-beach-bonfire.jpg
hotel-infinity-pool-panorama.jpg
kayaking-in-blue-lagoon.jpg
local-market-fruit-stall.jpg
mountain-trail-hiking-group.jpg
snorkeling-coral-reef-underwater.jpg
sunset-silhouette-pier.jpg
temple-visit-golden-pagoda.jpg
underwater-turtle-encounter.jpg
volcano-viewpoint-morning.jpg
waterfall-swimming-hole.jpg
```

Each name is distinct, descriptive, and collectively they paint a complete picture of the vacation.

### Holistic Naming Prompt Design

The holistic naming prompt is sent ONCE per folder, containing ALL file summaries from the content analysis phase:

```
You are a file naming specialist. You are renaming ALL files in a
single folder as a cohesive set. Each name must be unique, descriptive,
and complementary to the others.

FOLDER CONTEXT:
- Folder path: {full_folder_path}
- Folder hierarchy: {breadcrumb_path}
  (e.g., "hard-drive / documents / work / 2023 / q3-reports")
- Folder name: {folder_name}
- Total files in folder: {count}

FILE SUMMARIES:
(For each file, the structured summary from the analysis phase)

File 1:
  Current name: {current_name_1}
  Type: {content_type}
  Summary: {primary_subject}
  Key entities: {key_entities}
  Dates: {date_references}

File 2:
  Current name: {current_name_2}
  ...

NAMING RULES:
(All rules from Section 8 are injected here)

INSTRUCTIONS:
1. Consider all files as a SET. Each name should occupy a distinct
   semantic niche within the folder's context.
2. Use the folder hierarchy as implicit context: don't repeat folder
   name information in file names. If the folder is "invoices-2023",
   don't name files "invoice-january-2023.pdf". Just "january.pdf"
   or "january-acme-corp.pdf" is sufficient.
3. If files form a natural sequence (chapters, months, versions),
   use consistent naming with sequence indicators.
4. Ensure NO two files get the same name.
5. If the current file name is already descriptive and accurate,
   you may keep it (return it unchanged).

Respond in this exact JSON format:
{
  "folder_context_summary": "brief description of what this folder contains",
  "naming_strategy": "brief description of naming approach chosen",
  "renames": [
    {
      "current_name": "original_filename.ext",
      "proposed_name": "new-descriptive-name.ext",
      "reasoning": "why this name was chosen",
      "confidence": 0.0-1.0
    },
    ...
  ]
}
```

### Scaling the Holistic Approach

The holistic approach works brilliantly for folders with up to ~50 files. Beyond that, the context window becomes a limiting factor and the quality of naming degrades. The scaling strategy:

| Folder Size | Strategy |
|-------------|----------|
| 1-50 files | **Full holistic.** All file summaries sent in a single naming prompt. |
| 51-200 files | **Clustered holistic.** Files are grouped by detected content type or thematic similarity (from the analysis phase). Each cluster is named holistically, with a "folder overview" preamble that describes the other clusters. |
| 201-500 files | **Sampled holistic.** A representative sample of ~50 files is analyzed and named holistically to establish naming patterns. The patterns are then applied to remaining files individually, with collision detection. |
| 500+ files | **Progressive holistic.** The folder is divided into batches of 50. Each batch is named holistically, with each successive batch receiving the names from prior batches as context to avoid collisions and maintain consistency. |

### Clustering Algorithm (for 51-200 files)

When a folder has more files than can fit in a single holistic prompt:

1. **Cluster by content type.** Group all images together, all PDFs together, etc.
2. **Within content types, cluster by semantic similarity.** Using the content summaries from the analysis phase, compute simple keyword overlap to group related files. This is NOT a vector embedding search: it is simple TF-IDF or keyword matching on the summaries, keeping the tool lightweight.
3. **Name each cluster holistically**, providing a folder-level preamble that lists ALL cluster names so the model knows what other groups exist.

---

## 10. Safety & Failsafe Mechanisms

File safety is the highest priority. A renamed file that is lost or corrupted is infinitely worse than a file with a bad name.

### Atomic Rename Protocol

Each file rename follows this exact sequence:

```python
# PSEUDOCODE: Atomic rename protocol

def safe_rename(old_path, new_path, manifest):
    # 1. Pre-flight checks
    assert old_path.exists(), "Source file missing"
    assert not new_path.exists(), "Target name already exists"
    assert old_path.parent == new_path.parent, "Cross-directory rename not allowed"

    old_size = old_path.stat().st_size
    old_inode = old_path.stat().st_ino  # Unix only, skip on Windows

    # 2. Record intent in manifest BEFORE rename
    manifest.record_intent(old_path, new_path, old_size)
    manifest.flush()  # Force write to disk

    # 3. Execute rename
    os.rename(old_path, new_path)
    # os.rename is atomic on same filesystem (POSIX guarantee)

    # 4. Post-rename verification
    assert new_path.exists(), "New file not found after rename"
    assert not old_path.exists(), "Old file still exists after rename"
    new_size = new_path.stat().st_size
    assert new_size == old_size, "File size changed during rename"

    # 5. Record success in manifest
    manifest.record_success(old_path, new_path)
    manifest.flush()
```

### Key Safety Properties

1. **Same-filesystem guarantee.** `os.rename()` is atomic on POSIX systems when source and destination are on the same filesystem. Since we only rename within the same directory (never move across directories), this is always satisfied.

2. **Manifest-before-rename.** The intent is written to the manifest file and flushed to disk BEFORE the rename executes. If the process crashes mid-rename, the manifest records what was attempted.

3. **Post-rename verification.** After every rename, the tool verifies the new file exists, the old file is gone, and the file size is unchanged. If any check fails, the operation halts immediately.

4. **Halt-on-first-failure.** If any single rename fails, the tool stops processing the entire batch. It does NOT continue with remaining files, because later files may depend on the context of earlier renames. The manifest preserves the state so the user can investigate and either retry or undo.

### What Happens on Failure

| Failure Scenario | Tool Behavior |
|-----------------|---------------|
| Process crash during rename | Manifest on disk records the intent. On next run, tool detects incomplete state and offers recovery options. |
| `os.rename()` raises exception | Exception caught. Old file untouched. Manifest records failure. Batch halts. |
| Post-rename verification fails | Alert raised. Manual intervention suggested. Manifest records the anomaly. |
| Disk full during manifest write | Tool detects write failure and refuses to proceed with renames until disk space is available. |
| Permission denied | Tool reports which files lack write permission. Suggests `chmod` or running with appropriate privileges. |

### No-Clobber Guarantee

The tool NEVER overwrites an existing file. If the proposed new name already exists:

1. First, check if the existing file and the file being renamed have identical content (same size + hash). If yes, this is a potential duplicate: flag it to the user but do NOT rename or delete either.
2. If they differ, append a numeric suffix: `report-quarterly-2023.pdf` -> `report-quarterly-2023-2.pdf`.
3. Numeric suffixes are applied DURING the validation phase (before execution), so the user sees them in the dry-run preview.

---

## 11. State Management

### Two-Tier State Model

The tool maintains state at two levels:

#### Tier 1: Ephemeral Working Manifest (Per-Run)

- **Location:** `{target_directory}/.ai-rename-manifest.json`
- **Lifecycle:** Created at start of execution phase. Deleted after successful completion. Persists on failure.
- **Purpose:** Enables undo within an active session and recovery from crashes.
- **Content:**

```json
{
  "version": "1.0",
  "session_id": "uuid-v4",
  "started_at": "2026-02-25T14:30:00Z",
  "target_directory": "/Users/user/documents/research/",
  "status": "in_progress",
  "renames": [
    {
      "index": 0,
      "old_name": "paper_v2_final.pdf",
      "new_name": "attention-is-all-you-need-2017.pdf",
      "old_path": "/Users/user/documents/research/paper_v2_final.pdf",
      "new_path": "/Users/user/documents/research/attention-is-all-you-need-2017.pdf",
      "file_size_bytes": 2048576,
      "status": "completed",
      "completed_at": "2026-02-25T14:30:05Z"
    },
    {
      "index": 1,
      "old_name": "download(3).pdf",
      "new_name": "bert-pretraining-devlin-2018.pdf",
      "status": "pending"
    }
  ]
}
```

- **Behavior in headless mode:** The manifest still exists on disk during execution but is automatically cleaned up on success. If the process is interrupted, the manifest remains for inspection.

#### Tier 2: Persistent Global Log (Append-Only)

- **Location:** `{tool_install_directory}/logs/rename-history.jsonl` (JSONL format: one JSON object per line)
- **Lifecycle:** Permanent. Never deleted. Append-only.
- **Purpose:** Audit trail. Enables querying rename history across all sessions. Supports multiple concurrent instances operating on different directories without conflict.
- **Concurrency safety:** The log file uses JSONL (one record per line) with file-level locking (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) to ensure atomic appends. Multiple instances of the tool running simultaneously against different directories will safely interleave their log entries without corruption.
- **Content (per line):**

```json
{
  "run_id": "uuid-v4",
  "run_started_at": "2026-02-25T14:28:00Z",
  "run_completed_at": "2026-02-25T14:30:05Z",
  "hostname": "macbook-pro.local",
  "username": "user",
  "pid": 42310,
  "tool_version": "1.0.0",
  "target_directory": "/Users/user/documents/research/",
  "target_directory_resolved": "/Volumes/ExternalHD/documents/research/",
  "recursive": true,
  "model_used": "gemini-2.0-flash",
  "files_discovered": 50,
  "files_renamed": 47,
  "files_skipped": 3,
  "files_failed": 0,
  "symlinks_updated": 2,
  "duration_seconds": 120,
  "total_tokens_used": 145320,
  "estimated_cost_usd": 0.28,
  "custom_instructions": null,
  "renames": [
    {
      "old": "paper_v2_final.pdf",
      "new": "attention-is-all-you-need-2017.pdf",
      "file_size_bytes": 2048576,
      "content_type": "document"
    }
  ]
}
```

**Run ID uniqueness:** The `run_id` is a UUID v4 generated at session start. It is used to correlate the ephemeral manifest with the permanent log entry. If multiple instances run simultaneously, each has a unique `run_id`, and the log entries are independent.

**Source tracking:** The `target_directory` and `target_directory_resolved` (symlink-resolved absolute path) fields ensure that when reviewing logs, it is always clear WHERE a rename operation was initiated, even if the same directory is mounted at different paths on different machines.

### Undo Mechanism

The `ai-rename undo` command works as follows:

1. **Check for ephemeral manifest** in the current directory (or specified directory).
2. If manifest exists and `status` is `"completed"`:
   - Display the list of renames that were performed.
   - Ask for confirmation to undo.
   - Reverse each rename in **reverse order** (last renamed file is un-renamed first).
   - Each undo operation follows the same atomic protocol (manifest-before-rename, post-verification).
3. If manifest exists and `status` is `"in_progress"`:
   - This indicates a crash or interruption.
   - Display which renames completed and which were pending.
   - Offer options: "Undo completed renames" or "Resume pending renames."
4. If no manifest exists:
   - Report that there is nothing to undo.
   - Suggest checking the global log for historical renames (which would require manual reversal).

### Manifest Lifecycle

```
CLI invoked
    │
    ├─── Interactive mode ──────────────────────┐
    │    │                                       │
    │    ├── Execution starts                    │
    │    │   └── Manifest CREATED                │
    │    │                                       │
    │    ├── All renames complete                 │
    │    │   └── Manifest status = "completed"   │
    │    │                                       │
    │    ├── User confirms satisfaction           │
    │    │   └── Manifest DELETED                 │
    │    │       Global log APPENDED              │
    │    │                                       │
    │    └── User runs "undo"                    │
    │        └── Renames reversed                │
    │            Manifest DELETED                │
    │            Global log APPENDED (undo)      │
    │                                            │
    └─── Headless mode ─────────────────────────┘
         │
         ├── Execution starts
         │   └── Manifest CREATED
         │
         ├── All renames complete
         │   └── Manifest status = "completed"
         │       Manifest DELETED
         │       Global log APPENDED
         │
         └── Process interrupted
             └── Manifest PERSISTS on disk
                 (recovery on next run)
```

---

## 12. CLI Interface Design

### Installation

```bash
pip install ai-file-rename
```

Or for development:

```bash
git clone <repo>
cd ai-file-rename
pip install -e .
```

### Commands & Flags

#### Primary Command: `ai-rename`

```
ai-rename <target-directory> [options]
```

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--recursive` | `-r` | `false` | Process subdirectories recursively |
| `--dry-run` | `-d` | `true` | Show proposed renames without executing (this is the DEFAULT) |
| `--execute` | `-x` | `false` | Execute renames (skip dry-run preview). Requires explicit opt-in. |
| `--headless` | `-H` | `false` | No interactive prompts. Auto-confirm everything. Implies `--execute`. |
| `--config` | `-c` | `~/.ai-rename.yaml` | Path to configuration file |
| `--model` | `-m` | `gemini-2.0-flash` | Gemini model to use |
| `--max-files` | | `500` | Safety limit: refuse to process more files than this |
| `--include` | | `*` | Glob pattern for files to include |
| `--exclude` | | | Glob pattern for files to exclude |
| `--skip-converted` | | `false` | Skip format conversion step (process only natively supported formats) |
| `--verbose` | `-v` | `false` | Verbose output with per-file processing details |
| `--log-level` | | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `--cost-limit` | | `5.00` | Maximum estimated API cost in USD before requiring confirmation |
| `--custom-instructions` | `-i` | | Additional naming instructions (e.g., "prefix all with project name") |

#### Undo Command: `ai-rename undo`

```
ai-rename undo [target-directory]
```

Reverses the last rename operation in the specified directory (or current directory).

| Flag | Short | Description |
|------|-------|-------------|
| `--force` | `-f` | Undo without confirmation prompt |

#### History Command: `ai-rename history`

```
ai-rename history [options]
```

Query the global rename log.

| Flag | Short | Description |
|------|-------|-------------|
| `--directory` | `-d` | Filter by target directory |
| `--last` | `-n` | Show last N sessions |
| `--json` | | Output as JSON |

### Programmatic API

For use as a Python library:

```python
from ai_file_rename import RenameSession

session = RenameSession(
    target_dir="~/documents/research/",
    recursive=True,
    api_key="...",
    model="gemini-2.0-flash"
)

# Step 1: Discover and analyze
plan = session.analyze()

# Step 2: Review proposed renames
for rename in plan.renames:
    print(f"{rename.old_name} -> {rename.proposed_name} ({rename.confidence})")

# Step 3: Execute
result = session.execute(plan)

# Step 4: Undo if needed
session.undo()
```

---

## 13. Gemini SDK Integration

### SDK: `google-genai`

The tool uses the unified `google-genai` Python SDK, which supports both Google AI Studio (API key) and Vertex AI (service account) through the same interface.

**Default: Google AI Studio (API key).** This is simpler and sufficient for all multimodal file processing needs. The multimodal capabilities are identical between Google AI Studio and Vertex AI, they use the same underlying models.

### Authentication

```python
from google import genai

# Google AI Studio (default: API key)
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Vertex AI (optional: service account)
client = genai.Client(
    vertexai=True,
    project="my-project",
    location="us-central1"
)
```

The tool reads the API key from:
1. `--api-key` flag (highest priority)
2. `GEMINI_API_KEY` environment variable
3. Configuration file (`~/.ai-rename.yaml`)

### File Upload Flow

```python
# Upload file to Gemini File API
uploaded_file = client.files.upload(file=file_path)

# Wait for processing (for video/audio files)
while uploaded_file.state == "PROCESSING":
    time.sleep(2)
    uploaded_file = client.files.get(name=uploaded_file.name)

# Use in content generation
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=[prompt_text, uploaded_file]
)
```

### File API Constraints

| Constraint | Limit |
|-----------|-------|
| Max file size | 2 GB |
| Max total storage per project | 20 GB |
| File retention | 48 hours (auto-deleted) |
| Request size limit | 100 MB |
| PDF page limit | 1,000 pages |

### Model Selection

| Model | Use Case | Cost | Speed |
|-------|----------|------|-------|
| `gemini-2.0-flash` | **Default.** Best balance of quality, speed, and cost for file analysis. | Low | Fast |
| `gemini-2.5-flash` | Higher quality analysis for complex documents. | Medium | Medium |
| `gemini-2.5-pro` | Maximum quality for difficult-to-analyze files. | Higher | Slower |

The default model (`gemini-2.0-flash`) is recommended for the file renaming use case because:
- File naming does not require deep reasoning: it requires breadth (understanding many file types) and precision (extracting key identifiers).
- Flash models process files faster, which matters when processing hundreds of files.
- Cost is lower, enabling batch processing without budget concerns.

### Rate Limiting & Retry

The tool implements exponential backoff with jitter for API calls:

```
Attempt 1: immediate
Attempt 2: wait 1-2 seconds
Attempt 3: wait 2-4 seconds
Attempt 4: wait 4-8 seconds
Attempt 5: wait 8-16 seconds
(max 5 retries, then fail)
```

Rate limits are respected by tracking API calls per minute and throttling if approaching the limit. The Gemini API rate limits vary by model and tier.

### Structured Output

All Gemini responses are requested as structured JSON using the `response_mime_type` parameter:

```python
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=[prompt, uploaded_file],
    config={
        "response_mime_type": "application/json",
        "response_schema": FileAnalysisSchema  # Pydantic model or dict
    }
)
```

This eliminates the need for fragile regex parsing of LLM output.

---

## 14. File Metadata Enrichment

### Rationale

File content alone does not tell the full story. A file's metadata: creation date, modification date, file size, author, embedded document title, EXIF camera data, audio duration: provides critical supplementary context that can make the difference between a generic name and a truly informative one.

**The metadata is NOT used directly in file names** (we don't name files `report-2023-12-01-4.2mb.pdf`). Instead, metadata is fed into the Gemini content analysis prompt as additional context, allowing the LLM to make better-informed decisions. For example:

| Metadata Signal | How It Helps Naming |
|----------------|---------------------|
| Created 2019-03-15 | The LLM knows this is a 2019 document and can reference the year if relevant |
| Author: "Dr. Sarah Chen" | The LLM can include the author name for academic papers |
| PDF title: "Q3 Earnings Call Transcript" | The LLM uses the embedded title as a strong naming signal |
| EXIF GPS: lat/long → "San Francisco, CA" | The LLM can name a photo `golden-gate-bridge-sunset.jpg` instead of `outdoor-scene.jpg` |
| File size: 250 MB | The LLM understands this is a substantial file (e.g., a full-length video, not a thumbnail) |
| Audio duration: 01:32:45 | The LLM knows this is a long-form recording (lecture, podcast) vs a short clip |
| Image dimensions: 3840x2160 | The LLM can distinguish a high-res photo from a small icon/thumbnail |

### Metadata Extraction Strategy

Metadata extraction happens BEFORE the Gemini API call, during the preprocessing phase. It is a best-effort operation: if extraction fails for any file, the tool proceeds with whatever metadata is available (at minimum, `os.stat` data is always available).

#### Universal Metadata (All Files)

Extracted via Python's `os.stat()` / `pathlib.Path.stat()`:

```python
{
  "file_size_bytes": 4194304,
  "file_size_human": "4.0 MB",
  "created_at": "2019-03-15T10:30:00Z",      # st_birthtime (macOS) or st_ctime (Linux/Windows)
  "modified_at": "2019-03-15T14:22:00Z",      # st_mtime
  "accessed_at": "2026-02-25T09:00:00Z",      # st_atime
  "is_symlink": false,
  "symlink_target": null,
  "permissions": "rw-r--r--",
  "hard_link_count": 1
}
```

**Note on `os.rename()` and metadata preservation:** Verified that `os.rename()` preserves ALL file metadata (inode, mtime, birthtime, size, permissions). This is because `os.rename()` on the same filesystem is a directory entry operation: it does not copy the file, so all metadata remains intact.

#### Format-Specific Metadata

| File Format | Library | Extracted Fields |
|-------------|---------|-----------------|
| **JPEG/PNG/HEIC/TIFF** | `Pillow` (EXIF) | Camera make/model, date taken, GPS coordinates (reverse-geocoded to city/country), image dimensions, orientation, focal length, exposure |
| **PDF** | `PyPDF2` or `pdfplumber` | Title, author, subject, creator application, creation date, modification date, page count, is encrypted |
| **DOCX** | `python-docx` | Title, author, subject, created date, modified date, last modified by, revision number, page count (approximate), word count |
| **PPTX** | `python-pptx` | Title, author, subject, created date, modified date, slide count |
| **XLSX** | `openpyxl` | Title, author, created date, modified date, sheet names, sheet count |
| **MP3** | `mutagen` | Title, artist, album, year, genre, duration, bitrate, track number |
| **MP4/MOV/AVI** | `mutagen` or `ffprobe` | Title, duration, video resolution, codec, frame rate, audio channels |
| **WAV/FLAC/OGG** | `mutagen` | Duration, sample rate, channels, bitrate |

#### Metadata Extraction is Best-Effort

- If a metadata library is not installed, the tool falls back to `os.stat` only and logs a warning.
- If a file is corrupted and metadata extraction fails, the tool logs the error and proceeds with `os.stat` metadata only.
- Metadata extraction must NOT block or slow down the pipeline. It runs with a per-file timeout of 5 seconds.
- The extracted metadata is structured as a JSON object and injected into the Gemini content analysis prompt.

#### GPS Reverse Geocoding (Optional)

For images with EXIF GPS data, the tool can optionally reverse-geocode coordinates to a human-readable location (e.g., "San Francisco, California, USA"). This uses a lightweight local database (no API call needed):

- **Library:** `reverse_geocoder` (offline, ships with a 30 MB GeoNames database)
- **Fallback:** If the library is not installed, raw GPS coordinates are passed to Gemini, which can often interpret them.
- **Privacy note:** GPS data is sent to Gemini as part of the prompt but is NOT stored in logs or manifests.

---

## 15. Supported File Types & Processing Strategies

### Tier 1: Directly Processable (Gemini Native)

These formats are uploaded to the Gemini File API as-is.

| Format | MIME Type | Gemini Capability |
|--------|-----------|-------------------|
| JPEG | `image/jpeg` | Full visual understanding |
| PNG | `image/png` | Full visual understanding |
| WebP | `image/webp` | Full visual understanding |
| HEIC | `image/heic` | Full visual understanding |
| HEIF | `image/heif` | Full visual understanding |
| PDF | `application/pdf` | Full visual understanding (charts, tables, diagrams, text) |
| MP3 | `audio/mp3` | Audio transcription + understanding |
| WAV | `audio/wav` | Audio transcription + understanding |
| AAC | `audio/aac` | Audio transcription + understanding |
| OGG | `audio/ogg` | Audio transcription + understanding |
| FLAC | `audio/flac` | Audio transcription + understanding |
| AIFF | `audio/aiff` | Audio transcription + understanding |
| MP4 | `video/mp4` | Visual + audio understanding |
| MOV | `video/mov` | Visual + audio understanding |
| AVI | `video/avi` | Visual + audio understanding |
| WebM | `video/webm` | Visual + audio understanding |
| WMV | `video/wmv` | Visual + audio understanding |
| MKV | `video/x-matroska` | Visual + audio understanding |
| FLV | `video/x-flv` | Visual + audio understanding |

### Tier 2: Convertible (Requires Pre-Processing)

These formats are NOT natively understood by Gemini in their original form (or only get degraded text extraction). The tool converts them to a natively supported format before uploading.

| Format | Conversion Target | Conversion Tool | Notes |
|--------|-------------------|-----------------|-------|
| SVG | PNG | `cairosvg` | Renders SVG to rasterized PNG |
| GIF | PNG (first frame) | `Pillow` | Extracts first frame; animated content noted in metadata |
| DOCX | PDF | `libreoffice --headless` or `docx2pdf` | Preserves visual formatting for Gemini vision |
| PPTX | PDF | `libreoffice --headless` or `pptx2pdf` | Preserves slide layouts and visual elements |
| XLSX | PDF | `libreoffice --headless` | Preserves table formatting and charts |
| BMP | PNG | `Pillow` | Simple format conversion |
| TIFF | PNG | `Pillow` | Simple format conversion |

**Important:** Conversions are performed to a temporary directory. Original files are NEVER modified. Temporary files are cleaned up after processing.

**LibreOffice dependency:** For DOCX/PPTX/XLSX conversion, the tool requires LibreOffice installed on the system. If LibreOffice is not available, the tool falls back to plain text extraction and warns the user that naming quality for Office documents will be degraded.

### Tier 3: Text-Extractable

These are processed by reading their text content directly and sending it as a text prompt (no file upload needed).

| Format | Extraction Method |
|--------|-------------------|
| TXT | Direct read |
| MD | Direct read |
| HTML | HTML parser (strip tags, extract text) |
| XML | Direct read |
| JSON | Direct read |
| YAML | Direct read |
| CSV | Direct read (first 100 rows) |
| TSV | Direct read (first 100 rows) |
| Source code (`.py`, `.js`, `.rs`, etc.) | Direct read (first 500 lines) |
| LOG | Direct read (last 200 lines) |

### Tier 4: Unsupported (Skipped)

These are logged and skipped with a warning.

| Category | Examples |
|----------|---------|
| Archives | `.zip`, `.tar`, `.gz`, `.rar`, `.7z` |
| Executables | `.exe`, `.app`, `.dmg`, `.msi`, `.deb` |
| Disk images | `.iso`, `.img` |
| Database files | `.db`, `.sqlite`, `.mdb` |
| System files | `.dll`, `.so`, `.dylib`, `.sys` |
| Proprietary binary | `.psd`, `.ai`, `.sketch`, `.fig` |
| Font files | `.ttf`, `.otf`, `.woff` |
| 3D models | `.obj`, `.stl`, `.fbx` |

---

## 16. Scalability & Batching Strategy

### API Call Optimization

Processing each file requires at minimum 1 API call (content analysis), and each folder requires 1 additional call (holistic naming). For large directories, this adds up.

#### Batching Content Analysis

Multiple files can be analyzed in a single API call if they are small enough. The tool implements intelligent batching:

```
Per-call budget: 100 MB (Gemini request limit)

For each folder:
  Sort files by size (ascending)
  Create batches where total size < 80 MB (with 20% safety margin)
  Send each batch as a single API call with multiple files
```

For a batch of files, the prompt asks for a JSON array of summaries, one per file.

#### Concurrency

API calls can be parallelized across folders (since each folder is an independent naming context). The tool uses a configurable concurrency limit (default: 3 parallel requests) to balance speed against API rate limits.

```python
import asyncio

semaphore = asyncio.Semaphore(3)  # Max 3 concurrent API calls

async def process_folder(folder):
    async with semaphore:
        summaries = await analyze_files(folder.files)
        renames = await generate_names(folder, summaries)
        return renames

# Process all folders concurrently (within semaphore limit)
results = await asyncio.gather(*[
    process_folder(f) for f in folders
])
```

### Progress Reporting

For large operations, the tool displays a progress bar:

```
Processing: ~/documents/research/
[████████████████████░░░░░░░░░░░░] 67% │ 156/231 files │ ETA: 2m 14s
Current: analyzing quantum-computing-slides.pptx (converting to PDF...)
```

---

## 17. Configuration & Customization

### Configuration File

The tool reads from `~/.ai-rename.yaml` (or a path specified via `--config`):

```yaml
# ~/.ai-rename.yaml

# Authentication
gemini_api_key: "YOUR_API_KEY"     # Or use GEMINI_API_KEY env var
# vertex_ai_project: "my-project"  # Uncomment to use Vertex AI
# vertex_ai_location: "us-central1"

# Model
model: "gemini-2.0-flash"

# Naming preferences
naming:
  max_words: 8          # Maximum words in a file name
  min_words: 2          # Minimum words in a file name
  separator: "-"        # Word separator (hyphen is default)
  include_dates: true   # Include dates found in content
  language: "en"        # Target language for file names
  custom_instructions: ""  # Additional instructions for the naming prompt

# Safety
safety:
  max_files: 500        # Refuse to process more than this many files
  cost_limit: 5.00      # Maximum estimated cost before requiring confirmation
  require_confirmation: true  # Always require confirmation before execution

# Processing
processing:
  concurrency: 3           # Max parallel API calls
  convert_office_docs: true # Convert DOCX/PPTX/XLSX to PDF before analysis

# Logging
logging:
  level: "INFO"
  log_dir: "~/.ai-rename/logs/"   # Where global logs are stored

# Exclude patterns (glob)
exclude_patterns:
  - ".*"           # Hidden files
  - "*.tmp"        # Temp files
  - "node_modules" # Dependency directories
  - "__pycache__"  # Python cache
  - ".git"         # Git directories
```

### Custom Naming Instructions

Users can inject custom instructions that are appended to the naming prompt:

```bash
ai-rename ~/projects/website/ --custom-instructions "Prefix all files with 'web-'. Use the pattern: web-{page}-{element}.{ext}"
```

This allows domain-specific naming conventions without modifying the tool's core logic.

---

## 18. Logging & Observability

### Log Levels

| Level | What Gets Logged |
|-------|-----------------|
| `DEBUG` | Every API call, every file operation, prompt/response pairs, timing |
| `INFO` | File discovered, file analyzed, rename proposed, rename executed |
| `WARNING` | Unsupported file skipped, conversion failed (fallback used), name collision resolved |
| `ERROR` | Rename failed, API call failed after retries, manifest write failure |

### Log Destinations

1. **Terminal output**: Real-time progress and results.
2. **Session log file**: Per-run detailed log: `~/.ai-rename/logs/session-{session_id}.log`
3. **Global rename history**: Append-only JSONL: `~/.ai-rename/logs/rename-history.jsonl`

### Cost Tracking

Every API call logs its token usage. At the end of a session, the tool reports:

```
Session Summary:
  Files processed:  231
  Files renamed:    228
  Files skipped:      3
  API calls:         52
  Tokens used:  145,320 (input: 128,000 / output: 17,320)
  Estimated cost:  $0.28
  Duration:      3m 42s
```

---

## 19. Error Handling & Edge Cases

### Edge Cases & How They Are Handled

| Edge Case | Handling |
|-----------|----------|
| **Empty folder** | Report "no files to process" and exit cleanly. |
| **Single file in folder** | Skip holistic naming. Name based on content analysis alone. |
| **File with no extension** | Attempt to detect MIME type via magic bytes. If type is determined, process normally. If unknown, skip with warning. |
| **Extremely large file (>2 GB)** | Skip with warning (exceeds Gemini File API limit). |
| **Corrupt/unreadable file** | Skip with warning. Do not halt the batch. |
| **File name is already the proposed name** | Skip (no-op). Report as "unchanged." |
| **Two files would get the same name** | Append numeric suffix to the second file. Report the collision. |
| **File is a symlink** | **Safe to rename.** Renaming a symlink via `os.rename()` only changes the link's name: the internal target path is unchanged, the link still resolves correctly. The tool processes and renames symlinks just like regular files. However, the content analysis step reads the *target* file's content (via the symlink), so the generated name describes the target's content, which is correct. |
| **File is a symlink TARGET** | **DANGER.** If a regular file has incoming symlinks pointing to it, renaming the file breaks those symlinks (they become dangling). During discovery, the tool scans for symlinks in the target directory and builds a reverse map of `file -> [symlinks pointing to it]`. If a file is a symlink target: (1) warn the user in the dry-run preview, (2) if the user confirms, update all affected symlinks to point to the new name after the rename. This is an additional atomic step in the execution phase. |
| **Symlink points outside target directory** | The symlink itself is renamable (safe). The target is not modified. The content analysis reads the external target for context. The tool notes in the dry-run that this symlink references an external path. |
| **Insufficient permissions** | Report which files are not writable. Do not attempt rename. |
| **File is open/locked by another process** | On Windows, this will cause `os.rename()` to fail. Catch the exception, report it, and continue with next file (exception to halt-on-failure for this specific case). |
| **Network failure during API call** | Retry with exponential backoff (max 5 retries). If all retries fail, skip the file and continue. |
| **Gemini returns invalid JSON** | Retry once. If still invalid, skip the file. |
| **Gemini hallucinates content** | Content accuracy is verified by confidence score. Low-confidence results are flagged in the dry-run preview. |
| **File name would exceed OS limits** | Truncate intelligently (keep meaningful words, drop from the end). |
| **File contains sensitive/private content** | The tool does NOT store file content. Content summaries are ephemeral (in-memory during the session). Only file names are logged permanently. Gemini File API auto-deletes uploaded files after 48 hours. |
| **Target directory is a mount point/network drive** | Warn that `os.rename()` atomicity is not guaranteed on network file systems. Suggest using `--verify-checksums` flag for additional safety. |
| **Very deep folder nesting (>10 levels)** | Process normally. The full breadcrumb path is included in context regardless of depth. |
| **Mixed language files** | The naming language defaults to English but can be configured. The tool detects the content language and reports it. |
| **Unicode file names** | Current names with Unicode characters are handled correctly by Python's pathlib. Generated names are transliterated to ASCII for cross-platform safety. |
| **Race condition: file modified during processing** | The tool checks file modification time before and after analysis. If the file was modified during processing, it is skipped with a warning. |

### Error Recovery Protocol

If the tool crashes or is interrupted mid-execution:

1. On next invocation targeting the same directory, the tool detects the leftover `.ai-rename-manifest.json`.
2. It parses the manifest to determine:
   - Which renames completed successfully.
   - Which rename was in progress (if any).
   - Which renames were still pending.
3. It offers the user three options:
   - **Resume:** Continue from where it left off.
   - **Undo:** Reverse all completed renames.
   - **Discard:** Delete the manifest and start fresh (no renames undone).

---

## 20. Cross-Platform Compatibility

### File System Differences

| Aspect | Windows | macOS | Linux |
|--------|---------|-------|-------|
| Case sensitivity | Case-insensitive | Case-insensitive (default) | Case-sensitive |
| Path separator | `\` | `/` | `/` |
| Max path length | 260 chars (default) | 1024 chars | 4096 chars |
| Max filename length | 255 chars | 255 chars | 255 chars |
| Forbidden chars | `< > : " / \ \| ? *` | `/` `:` | `/` `NUL` |
| Reserved names | `CON PRN AUX NUL COM1-9 LPT1-9` | None | None |

### Cross-Platform Strategy

The tool uses the **intersection of all restrictions**: the most restrictive rule from any platform applies universally:

- Max filename: **200 characters** (conservative, leaving room for path)
- Forbidden chars: `< > : " / \ | ? * NUL` (union of all platforms)
- Case: **all lowercase** (avoids macOS/Windows case-insensitivity issues)
- Reserved names: **Windows reserved names avoided** (even on Linux/macOS)
- Path handling: **Python `pathlib.Path`** throughout (handles separators automatically)

This means a file renamed on macOS will have a valid name when the hard drive is accessed from a Windows or Linux machine.

---

## 21. Security Considerations

### API Key Management

- The API key is read from environment variable or config file. It is NEVER logged, NEVER included in manifests, and NEVER printed to the terminal.
- The config file (`~/.ai-rename.yaml`) should have restrictive permissions (`600`). The tool warns if it doesn't.

### File Content Privacy

- File content is sent to Google's Gemini API for analysis. Users should be aware of Google's data usage policies.
- The tool does NOT store file content locally. Content summaries are in-memory only during the session.
- Uploaded files are auto-deleted by the Gemini File API after 48 hours.
- The global log records ONLY file names (old and new), NEVER file content or summaries.

### Path Traversal Prevention

- The tool validates that all file paths are within the specified target directory.
- Symlinks are not followed (to prevent escaping the target directory).
- The `--recursive` flag only descends into real subdirectories, not symlink targets.

### Injection Prevention

- File names are sanitized before any shell operations (though the tool avoids shell operations: it uses Python's `os.rename()` and `pathlib` directly).
- Generated file names are validated against the cross-platform naming rules before execution.

---

## 22. Testing Strategy

### Test Categories

| Category | What Is Tested | Example |
|----------|---------------|---------|
| **Unit tests** | Individual components (validator, namer, executor) | Name validation rejects forbidden characters |
| **Integration tests** | End-to-end workflow with mock Gemini responses | Full pipeline from discovery to rename with fixture files |
| **Safety tests** | Failure scenarios and recovery | Simulate crash mid-rename, verify manifest enables recovery |
| **Cross-platform tests** | Generated names work on all platforms | Name validator catches Windows-reserved names on Linux |
| **Edge case tests** | All edge cases from Section 18 | Empty folder, single file, name collision, corrupt file |

### Test Fixtures

A `tests/fixtures/` directory contains sample files of each supported type:
- Tiny JPEG, PNG, PDF, DOCX, etc. (under 1 KB each, with known content)
- Files with deliberately bad names (UUID names, `download(1).pdf`, etc.)
- Files with Unicode names
- Nested folder structures

### Mock Strategy

Gemini API calls are mocked in tests using recorded responses. This ensures:
- Tests run without an API key.
- Tests are deterministic and fast.
- Edge cases in API responses can be simulated (rate limits, invalid JSON, etc.).

---

## 23. Tech Stack & Dependencies

### Core Dependencies

| Package | Purpose | Version |
|---------|---------|---------|
| `google-genai` | Gemini SDK (file upload, content generation) | Latest |
| `click` | CLI framework (commands, flags, help text) | >=8.0 |
| `rich` | Terminal formatting (tables, progress bars, colors) | >=13.0 |
| `pydantic` | Data models and validation | >=2.0 |
| `pyyaml` | Configuration file parsing | >=6.0 |

### Optional Dependencies

| Package | Purpose | When Needed |
|---------|---------|-------------|
| `cairosvg` | SVG to PNG conversion | When processing SVG files |
| `Pillow` | GIF/BMP/TIFF to PNG conversion | When processing these image formats |
| `python-magic` | MIME type detection via magic bytes | When files have no extension |

### System Dependencies (Optional)

| Tool | Purpose | When Needed |
|------|---------|-------------|
| LibreOffice | DOCX/PPTX/XLSX to PDF conversion | When processing Office documents (for full visual analysis) |

### Python Version

- **Minimum: Python 3.10** (for `match` statements and modern typing)
- **Recommended: Python 3.11+** (for improved error messages and `tomllib`)

### Project Structure

```
ai-file-rename/
├── src/
│   └── ai_file_rename/
│       ├── __init__.py
│       ├── __main__.py          # python -m ai_file_rename
│       ├── cli.py
│       ├── discovery.py
│       ├── preprocessing.py
│       ├── context.py
│       ├── analyzer.py
│       ├── namer.py
│       ├── validator.py
│       ├── executor.py
│       ├── manifest.py
│       ├── logger.py
│       ├── config.py
│       ├── models.py
│       └── constants.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── sample-files/
│   │   └── mock-responses/
│   ├── test_discovery.py
│   ├── test_preprocessing.py
│   ├── test_context.py
│   ├── test_analyzer.py
│   ├── test_namer.py
│   ├── test_validator.py
│   ├── test_executor.py
│   ├── test_manifest.py
│   └── test_cli.py
├── docs/
│   └── PRD.md
├── pyproject.toml
├── README.md
├── LICENSE
└── .gitignore
```

---

## 24. Future Considerations

These are explicitly OUT OF SCOPE for v1 but documented for future reference:

| Feature | Description | Complexity |
|---------|-------------|------------|
| **Tag generation** | In addition to renaming, generate tags/labels stored in a sidecar file | Medium |
| **Folder restructuring** | Suggest or execute folder reorganization based on content analysis | High |
| **Deduplication** | Identify and flag/remove duplicate files | Medium |
| **Watch mode** | Monitor a folder for new files and auto-rename them | Medium |
| **GUI** | Web-based or native GUI for reviewing and approving renames | High |
| **Custom model support** | Allow using other LLM providers (OpenAI, Anthropic) for analysis | Medium |
| **Plugin system** | Allow custom naming strategies via Python plugins | Medium |
| **Incremental processing** | Remember previously processed files and skip them on re-runs | Low |
| **Content-based search** | After renaming, build a searchable index of file content summaries | High |

---

## 25. Appendix

### A. Example Prompt: Content Analysis (Image)

```
You are a file content analyzer. Your job is to produce a brief,
factual summary of this file's content that will be used to generate
a descriptive filename.

Context:
- This file is located at: /Users/user/photos/vacation-2023/IMG_20230815_142233.jpg
- Parent folder: vacation-2023
- Folder hierarchy: photos > vacation-2023
- Current filename: IMG_20230815_142233.jpg
- File type: image/jpeg
- File size: 4.2 MB
- Created date: 2023-08-15T14:22:33Z
- Last modified: 2023-08-15T14:22:33Z
- Last accessed: 2026-02-20T09:15:00Z
- Is symlink: false
- Embedded metadata:
  {
    "camera_make": "Apple",
    "camera_model": "iPhone 14 Pro",
    "date_taken": "2023-08-15T14:22:33",
    "gps_location": "Phuket, Thailand",
    "image_dimensions": "4032x3024",
    "focal_length": "6.86mm",
    "orientation": "landscape"
  }

Instructions:
- Describe the PRIMARY content/subject of this file in 2-3 sentences.
- Identify the TYPE of content (e.g., "photograph of...", "screenshot of...").
- Extract any key identifiers: dates, names, organizations, topics.
- Use the embedded metadata to enrich your understanding.
- Do NOT suggest a filename. Just describe the content.

Respond in this exact JSON format:
{
  "content_type": "photograph",
  "primary_subject": "A group of four people standing on a wooden pier at sunset in Phuket, Thailand. The lighting suggests golden hour, and the people appear to be posing for a group photo with the Andaman Sea in the background.",
  "key_entities": ["pier", "sunset", "group photo", "Phuket", "Thailand", "Andaman Sea"],
  "date_references": ["2023-08-15"],
  "language": "n/a",
  "confidence": 0.95
}
```

### B. Example Prompt: Holistic Naming (Folder of Mixed Media)

```
You are a file naming specialist. You are renaming ALL files in a
single folder as a cohesive set.

FOLDER CONTEXT:
- Folder path: /Users/user/work/2023-annual-report/
- Folder hierarchy: work > 2023-annual-report
- Folder name: 2023-annual-report
- Total files: 7

FILE SUMMARIES:

File 1:
  Current name: final_draft_v3.docx
  Type: document
  Size: 2.8 MB | Created: 2023-11-15 | Modified: 2023-12-01
  Metadata: {author: "Jane Thompson", title: "Acme Corp Annual Report FY2023", pages: 45}
  Summary: A 45-page annual report for Acme Corporation covering
           fiscal year 2023, including financial statements,
           executive summary, and strategic outlook.
  Key entities: ["Acme Corporation", "FY2023", "annual report", "Jane Thompson"]

File 2:
  Current name: chart_export.png
  Type: diagram
  Size: 340 KB | Created: 2023-11-20 | Modified: 2023-11-20
  Metadata: {dimensions: "1920x1080"}
  Summary: A bar chart showing quarterly revenue for 2023,
           with Q1-Q4 labeled and values in USD millions.
  Key entities: ["quarterly revenue", "bar chart", "2023"]

File 3:
  Current name: IMG_20231201_091500.jpg
  Type: photograph
  Size: 5.1 MB | Created: 2023-12-01 | Modified: 2023-12-01
  Metadata: {camera: "Canon EOS R5", date_taken: "2023-12-01", dimensions: "8192x5464"}
  Summary: A professional headshot of a woman in business attire
           against a neutral background. Appears to be the CEO.
  Key entities: ["headshot", "CEO", "professional photo"]

... (remaining files)

NAMING RULES:
- Lowercase, hyphen-separated, 2-8 words
- ASCII only, no forbidden characters
- The folder is already named "2023-annual-report", so don't
  repeat "annual report" in every file name
- Each name must be unique within this folder

RESPONSE FORMAT:
{
  "folder_context_summary": "Materials for Acme Corp's 2023 annual report",
  "naming_strategy": "Role-based naming since each file serves a distinct function in the report package",
  "renames": [
    {
      "current_name": "final_draft_v3.docx",
      "proposed_name": "full-report-acme-corp.docx",
      "reasoning": "Main report document. Includes company name for specificity.",
      "confidence": 0.95
    },
    {
      "current_name": "chart_export.png",
      "proposed_name": "quarterly-revenue-chart.png",
      "reasoning": "Describes the chart's specific content.",
      "confidence": 0.93
    },
    {
      "current_name": "IMG_20231201_091500.jpg",
      "proposed_name": "ceo-headshot.jpg",
      "reasoning": "Professional headshot, likely the CEO based on context.",
      "confidence": 0.78
    }
  ]
}
```

### C. Cross-Platform Name Validation Pseudocode

```python
import re
import unicodedata

FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = {
    'con', 'prn', 'aux', 'nul',
    'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
    'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9',
}
MAX_NAME_LENGTH = 200

def validate_and_sanitize(proposed_name: str, extension: str) -> str:
    """Validate and sanitize a proposed file name."""
    name = proposed_name.strip()

    # 1. Transliterate Unicode to ASCII
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')

    # 2. Lowercase
    name = name.lower()

    # 3. Replace forbidden characters with hyphens
    name = FORBIDDEN_CHARS.sub('-', name)

    # 4. Replace spaces and underscores with hyphens
    name = re.sub(r'[\s_]+', '-', name)

    # 5. Collapse multiple hyphens
    name = re.sub(r'-+', '-', name)

    # 6. Strip leading/trailing hyphens and dots
    name = name.strip('-.')

    # 7. Check for reserved names
    if name.split('.')[0] in WINDOWS_RESERVED:
        name = f"file-{name}"

    # 8. Truncate to max length (leaving room for extension)
    max_stem = MAX_NAME_LENGTH - len(extension) - 1  # -1 for the dot
    if len(name) > max_stem:
        # Truncate at last hyphen before limit to avoid cutting mid-word
        truncated = name[:max_stem]
        last_hyphen = truncated.rfind('-')
        if last_hyphen > max_stem // 2:
            name = truncated[:last_hyphen]
        else:
            name = truncated

    # 9. Handle leading dots (would make file hidden on Unix)
    if name.startswith('.'):
        name = f"_{name}"

    # 10. Final safety: if name is empty after sanitization
    if not name:
        name = "unnamed-file"

    return f"{name}.{extension}"
```

### D. Glossary

| Term | Definition |
|------|-----------|
| **Content analysis** | The process of uploading a file to Gemini and extracting a structured summary of its content. |
| **Holistic naming** | Generating file names for ALL files in a folder simultaneously, with awareness of each other, to ensure names are distinct and complementary. |
| **Naming context unit** | A single folder: the boundary within which files are named holistically. |
| **Manifest** | An ephemeral JSON file tracking the state of rename operations, enabling undo and crash recovery. |
| **Dry-run** | Displaying proposed renames without executing them. The default mode of operation. |
| **Atomic rename** | A rename operation guaranteed to either fully succeed or fully fail, with no intermediate state where the file is lost. |
| **Breadcrumb path** | The full folder hierarchy from the hard drive root to the current folder, providing naming context. |
| **Sibling files** | Other files in the same folder as the file being renamed. |

---

*End of PRD: v1.0.0*
