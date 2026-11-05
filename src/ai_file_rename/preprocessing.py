"""
Format conversion for ai-file-rename.

Converts files that Gemini cannot process natively into processable formats.
All conversions write to a temporary directory. Original files are NEVER modified.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ai_file_rename.config import Config
from ai_file_rename.models import EnrichedFile, FileCategory, FileEntry, FileMetadata
from ai_file_rename.metadata import extract_metadata


def _convert_svg_to_png(src: Path, dst: Path) -> bool:
    """Convert SVG to PNG using cairosvg."""
    try:
        import cairosvg
        cairosvg.svg2png(url=str(src), write_to=str(dst))
        return True
    except ImportError:
        return False
    except Exception:
        return False


def _convert_image_to_png(src: Path, dst: Path) -> bool:
    """Convert GIF/BMP/TIFF to PNG using Pillow."""
    try:
        from PIL import Image
        with Image.open(src) as img:
            # For GIFs, take the first frame
            img.save(dst, "PNG")
        return True
    except ImportError:
        return False
    except Exception:
        return False


def _convert_office_to_pdf(src: Path, dst: Path) -> bool:
    """Convert Office documents to PDF using LibreOffice headless."""
    try:
        # Find LibreOffice
        lo_path = shutil.which("libreoffice") or shutil.which("soffice")
        if lo_path is None:
            return False

        outdir = dst.parent

        result = subprocess.run(
            [
                lo_path,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(outdir),
                str(src),
            ],
            capture_output=True,
            timeout=60,
        )

        if result.returncode != 0:
            return False

        # LibreOffice names the output file with the same stem
        expected_output = outdir / f"{src.stem}.pdf"
        if expected_output.exists():
            if expected_output != dst:
                expected_output.rename(dst)
            return True

        return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


# Conversion dispatch table
CONVERSION_MAP: dict[str, tuple[str, callable]] = {
    "svg": ("png", _convert_svg_to_png),
    "gif": ("png", _convert_image_to_png),
    "bmp": ("png", _convert_image_to_png),
    "tiff": ("png", _convert_image_to_png),
    "tif": ("png", _convert_image_to_png),
    "docx": ("pdf", _convert_office_to_pdf),
    "pptx": ("pdf", _convert_office_to_pdf),
    "xlsx": ("pdf", _convert_office_to_pdf),
    "doc": ("pdf", _convert_office_to_pdf),
    "ppt": ("pdf", _convert_office_to_pdf),
    "xls": ("pdf", _convert_office_to_pdf),
}


def preprocess(
    files: list[FileEntry],
    temp_dir: Path,
    config: Config,
) -> list[EnrichedFile]:
    """
    Convert files to Gemini-compatible formats where needed.

    Files that are already processable pass through unchanged.
    Converted files get a `processed_path` pointing to the temp copy.
    Original files are NEVER modified.

    Args:
        files: List of discovered file entries.
        temp_dir: Temporary directory for converted files.
        config: Resolved configuration.

    Returns:
        List of EnrichedFile objects with metadata and processed paths.
    """
    temp_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for file_entry in files:
        if file_entry.skip_reason:
            # Skip files with known issues
            metadata = extract_metadata(file_entry)
            results.append(
                EnrichedFile(
                    entry=file_entry,
                    metadata=metadata,
                    processed_path=None,
                )
            )
            continue

        # Extract metadata for all files
        metadata = extract_metadata(file_entry)
        processed_path = None

        if file_entry.category == FileCategory.DIRECTLY_PROCESSABLE:
            # No conversion needed
            processed_path = file_entry.path

        elif file_entry.category == FileCategory.CONVERTIBLE:
            if not config.convert_office_docs and file_entry.extension in (
                "docx", "pptx", "xlsx", "doc", "ppt", "xls"
            ):
                # User opted out of office conversion: fall back to text extraction
                processed_path = None
            else:
                ext = file_entry.extension.lower()
                conversion = CONVERSION_MAP.get(ext)

                if conversion:
                    target_ext, converter = conversion
                    output_name = f"{file_entry.stem}_converted.{target_ext}"
                    output_path = temp_dir / output_name

                    success = converter(file_entry.path, output_path)
                    if success and output_path.exists():
                        processed_path = output_path
                    # If conversion fails, processed_path stays None (will use text fallback)

        elif file_entry.category == FileCategory.TEXT_EXTRACTABLE:
            # Text files don't need conversion: content is read inline
            processed_path = file_entry.path

        results.append(
            EnrichedFile(
                entry=file_entry,
                metadata=metadata,
                processed_path=processed_path,
            )
        )

    return results
