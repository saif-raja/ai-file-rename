# Known and Open Issues

Open items a reader or contributor should know about. Each names the code it concerns; when the code changes, this list changes in the same commit.

- **`undo` works only for interrupted or failed runs.** A run that completes with zero failures deletes its manifest (`executor.py`, finalize step; pinned by `tests/test_executor.py::test_manifest_cleanup_on_success`), and `undo` reads only the manifest, so after a clean run it reports nothing to undo. The completed run is in `~/.ai-rename/logs/rename-history.jsonl`, from which a reversal is a manual job. The PRD (`0-PRD.md`, Manifest Lifecycle) describes an interactive mode that keeps the manifest until the user confirms; that mode was not built.
- **`ruff check src tests` reports 49 findings** (38 unused imports, 7 f-strings without placeholders, 4 unused variables); all pre-date the public release and none affects behaviour. `uv run --frozen ruff check src tests --fix` clears 46 of them.
- **PyPDF2 is deprecated upstream** in favour of `pypdf`; the `pdf` extra still pins `PyPDF2>=3.0` and the test run reports the deprecation warning.
- **The design documents are design-time records.** `0-PRD.md` and `0-architecture.md` describe the system as planned (for example a default model of `gemini-2.0-flash`, an `--api-key` flag, and a single-file naming shortcut); the shipped defaults and flags are in `config.py` and `cli.py`. Where they differ, the code is right.
