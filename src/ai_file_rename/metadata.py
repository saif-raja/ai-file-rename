"""
Metadata extraction for ai-file-rename.

Extracts both OS-level and format-specific metadata from files.
All format-specific extractors use lazy imports and are best-effort.
"""

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from ai_file_rename.models import FileEntry, FileMetadata


def _format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _format_permissions(mode: int) -> str:
    """Format file mode as rwx string."""
    perms = ""
    for who in ("USR", "GRP", "OTH"):
        for what, letter in (("R", "r"), ("W", "w"), ("X", "x")):
            flag = getattr(stat, f"S_I{what}{who}", 0)
            perms += letter if mode & flag else "-"
    return perms


def _get_datetime(timestamp: float) -> Optional[datetime]:
    """Convert a Unix timestamp to datetime, handling errors."""
    try:
        return datetime.fromtimestamp(timestamp)
    except (OSError, ValueError, OverflowError):
        return None


def _extract_os_metadata(file_path: Path) -> dict:
    """Extract universal OS-level metadata using os.stat."""
    try:
        s = file_path.stat()
    except OSError:
        return {"size_bytes": 0, "size_human": "0 B"}

    result = {
        "size_bytes": s.st_size,
        "size_human": _format_size(s.st_size),
        "modified_at": _get_datetime(s.st_mtime),
        "accessed_at": _get_datetime(s.st_atime),
        "permissions": _format_permissions(s.st_mode),
    }

    # Birth time (macOS) or ctime (Linux/Windows)
    if hasattr(s, "st_birthtime"):
        result["created_at"] = _get_datetime(s.st_birthtime)
    else:
        result["created_at"] = _get_datetime(s.st_ctime)

    return result


def _with_timeout(func, timeout: float = 5.0, default=None):
    """Run a function with a timeout. Returns default on timeout."""
    if sys.platform == "win32":
        # Windows: use threading
        result = [default]
        exc = [None]

        def wrapper():
            try:
                result[0] = func()
            except Exception as e:
                exc[0] = e

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            return default
        if exc[0] is not None:
            return default
        return result[0]
    else:
        # POSIX: use signal.alarm
        def handler(signum, frame):
            raise TimeoutError()

        old_handler = signal.signal(signal.SIGALRM, handler)
        signal.alarm(int(timeout))
        try:
            result = func()
            signal.alarm(0)
            return result
        except (TimeoutError, Exception):
            signal.alarm(0)
            return default
        finally:
            signal.signal(signal.SIGALRM, old_handler)


# --- Format-specific extractors ---


def _extract_image_exif(file_path: Path) -> dict:
    """Extract EXIF data from JPEG/HEIC/TIFF images."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
    except ImportError:
        return {}

    result = {}
    try:
        with Image.open(file_path) as img:
            result["dimensions"] = f"{img.width}x{img.height}"

            exif_data = img.getexif()
            if not exif_data:
                return result

            exif_dict = {}
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                exif_dict[tag_name] = value

            if "Make" in exif_dict:
                result["camera_make"] = str(exif_dict["Make"]).strip()
            if "Model" in exif_dict:
                result["camera_model"] = str(exif_dict["Model"]).strip()
            if "DateTime" in exif_dict:
                try:
                    result["date_taken"] = datetime.strptime(
                        str(exif_dict["DateTime"]), "%Y:%m:%d %H:%M:%S"
                    )
                except ValueError:
                    pass
            if "Artist" in exif_dict:
                result["artist"] = str(exif_dict["Artist"]).strip()

            # GPS data
            gps_info = exif_data.get_ifd(0x8825)
            if gps_info:
                result["gps_location"] = _reverse_geocode_gps(gps_info)

    except Exception:
        pass

    return result


def _reverse_geocode_gps(gps_info: dict) -> Optional[str]:
    """Attempt to reverse-geocode GPS coordinates."""
    try:
        # Extract lat/lon from GPS IFD
        def to_degrees(values):
            d, m, s = values
            return float(d) + float(m) / 60 + float(s) / 3600

        lat_ref = gps_info.get(1, "N")
        lat = to_degrees(gps_info.get(2, (0, 0, 0)))
        lon_ref = gps_info.get(3, "E")
        lon = to_degrees(gps_info.get(4, (0, 0, 0)))

        if lat_ref == "S":
            lat = -lat
        if lon_ref == "W":
            lon = -lon

        # Try reverse geocoding
        try:
            import reverse_geocoder as rg
            results = rg.search((lat, lon))
            if results:
                r = results[0]
                return f"{r.get('name', '')}, {r.get('admin1', '')}, {r.get('cc', '')}"
        except ImportError:
            return f"{lat:.4f}, {lon:.4f}"

    except (TypeError, ValueError, KeyError):
        pass

    return None


def _extract_image_metadata(file_path: Path) -> dict:
    """Extract basic metadata from PNG and other images."""
    try:
        from PIL import Image
    except ImportError:
        return {}

    try:
        with Image.open(file_path) as img:
            return {"dimensions": f"{img.width}x{img.height}"}
    except Exception:
        return {}


def _extract_pdf_metadata(file_path: Path) -> dict:
    """Extract metadata from PDF files."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return {}

    result = {}
    try:
        reader = PdfReader(str(file_path))
        result["page_count"] = len(reader.pages)

        info = reader.metadata
        if info:
            if info.title:
                result["title"] = str(info.title)
            if info.author:
                result["author"] = str(info.author)
            if info.subject:
                result["subject"] = str(info.subject)
            if info.creator:
                result["creator_application"] = str(info.creator)
    except Exception:
        pass

    return result


def _extract_docx_metadata(file_path: Path) -> dict:
    """Extract metadata from DOCX files."""
    try:
        from docx import Document
    except ImportError:
        return {}

    result = {}
    try:
        doc = Document(str(file_path))
        props = doc.core_properties

        if props.title:
            result["title"] = props.title
        if props.author:
            result["author"] = props.author
        if props.subject:
            result["subject"] = props.subject
        if props.created:
            result["created_at"] = props.created
        if props.modified:
            result["modified_at"] = props.modified

        # Approximate word count
        word_count = 0
        for para in doc.paragraphs:
            word_count += len(para.text.split())
        result["word_count"] = word_count

    except Exception:
        pass

    return result


def _extract_pptx_metadata(file_path: Path) -> dict:
    """Extract metadata from PPTX files."""
    try:
        from pptx import Presentation
    except ImportError:
        return {}

    result = {}
    try:
        prs = Presentation(str(file_path))
        result["slide_count"] = len(prs.slides)

        props = prs.core_properties
        if props.title:
            result["title"] = props.title
        if props.author:
            result["author"] = props.author
    except Exception:
        pass

    return result


def _extract_xlsx_metadata(file_path: Path) -> dict:
    """Extract metadata from XLSX files."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return {}

    result = {}
    try:
        wb = load_workbook(str(file_path), read_only=True, data_only=True)
        result["sheet_names"] = wb.sheetnames

        props = wb.properties
        if props.title:
            result["title"] = props.title
        if props.creator:
            result["author"] = props.creator

        wb.close()
    except Exception:
        pass

    return result


def _extract_audio_metadata(file_path: Path) -> dict:
    """Extract metadata from audio files."""
    try:
        import mutagen
    except ImportError:
        return {}

    result = {}
    try:
        audio = mutagen.File(str(file_path))
        if audio is None:
            return {}

        if audio.info:
            if hasattr(audio.info, "length"):
                result["duration_seconds"] = audio.info.length
            if hasattr(audio.info, "bitrate"):
                result["bitrate"] = f"{audio.info.bitrate // 1000}kbps"

        # Common tags
        tag_map = {
            "title": ["TIT2", "title", "\xa9nam"],
            "artist": ["TPE1", "artist", "\xa9ART"],
            "album": ["TALB", "album", "\xa9alb"],
            "genre": ["TCON", "genre", "\xa9gen"],
        }

        for field, tag_names in tag_map.items():
            for tag_name in tag_names:
                if tag_name in (audio.tags or {}):
                    val = audio.tags[tag_name]
                    result[field] = str(val[0] if isinstance(val, list) else val)
                    break

    except Exception:
        pass

    return result


def _extract_legacy_office_metadata(file_path: Path) -> dict:
    """Extract metadata from legacy Office formats (DOC, PPT, XLS).

    Uses olefile to read OLE2 structured storage properties.
    Returns an empty dict if olefile is not installed or the file
    is not a valid OLE2 file.
    """
    try:
        import olefile
    except ImportError:
        return {}

    result = {}
    try:
        if not olefile.isOleFile(str(file_path)):
            return {}

        ole = olefile.OleFileIO(str(file_path))
        try:
            meta = ole.get_metadata()

            if meta.title:
                result["title"] = meta.title.decode("utf-8", errors="replace") if isinstance(meta.title, bytes) else str(meta.title)
            if meta.author:
                result["author"] = meta.author.decode("utf-8", errors="replace") if isinstance(meta.author, bytes) else str(meta.author)
            if meta.subject:
                result["subject"] = meta.subject.decode("utf-8", errors="replace") if isinstance(meta.subject, bytes) else str(meta.subject)
            if meta.creating_application:
                result["creator_application"] = (
                    meta.creating_application.decode("utf-8", errors="replace")
                    if isinstance(meta.creating_application, bytes)
                    else str(meta.creating_application)
                )
            if meta.create_time:
                result["created_at"] = meta.create_time
            if meta.last_saved_time:
                result["modified_at"] = meta.last_saved_time
            if hasattr(meta, "num_pages") and meta.num_pages:
                result["page_count"] = meta.num_pages
            if hasattr(meta, "num_words") and meta.num_words:
                result["word_count"] = meta.num_words
            if hasattr(meta, "num_slides") and meta.num_slides:
                result["slide_count"] = meta.num_slides
        finally:
            ole.close()
    except Exception:
        pass

    return result


def _extract_video_metadata_ffprobe(file_path: Path) -> dict:
    """Extract video metadata using ffprobe as a fallback.

    Runs ffprobe as a subprocess and parses the JSON output.
    Returns an empty dict if ffprobe is not installed or fails.
    """
    if not shutil.which("ffprobe"):
        return {}

    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(file_path),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            return {}

        data = json.loads(proc.stdout)
        result = {}

        # Extract from format section
        fmt = data.get("format", {})
        if "duration" in fmt:
            result["duration_seconds"] = float(fmt["duration"])
        if "bit_rate" in fmt:
            result["bitrate"] = f"{int(fmt['bit_rate']) // 1000}kbps"

        # Extract from video stream
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                if "codec_name" in stream:
                    result["codec"] = stream["codec_name"]
                width = stream.get("width")
                height = stream.get("height")
                if width and height:
                    result["dimensions"] = f"{width}x{height}"
                break

        return result
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception):
        return {}


def _extract_video_metadata(file_path: Path) -> dict:
    """Extract metadata from video files.

    Tries mutagen first (for MP4/MOV containers), then falls back
    to ffprobe subprocess if mutagen fails.
    """
    # Try mutagen first (for MP4/MOV containers)
    try:
        import mutagen
        video = mutagen.File(str(file_path))
        if video and video.info:
            result = {}
            if hasattr(video.info, "length"):
                result["duration_seconds"] = video.info.length
            if hasattr(video.info, "bitrate"):
                result["bitrate"] = f"{video.info.bitrate // 1000}kbps"
            if hasattr(video.info, "codec"):
                result["codec"] = video.info.codec
            if result:
                return result
    except Exception:
        pass

    # Fallback to ffprobe
    return _extract_video_metadata_ffprobe(file_path)


# Extractor dispatch table
EXTRACTORS = {
    "jpeg": _extract_image_exif,
    "jpg": _extract_image_exif,
    "png": _extract_image_metadata,
    "heic": _extract_image_exif,
    "tiff": _extract_image_exif,
    "tif": _extract_image_exif,
    "webp": _extract_image_metadata,
    "pdf": _extract_pdf_metadata,
    "docx": _extract_docx_metadata,
    "pptx": _extract_pptx_metadata,
    "xlsx": _extract_xlsx_metadata,
    "doc": _extract_legacy_office_metadata,
    "ppt": _extract_legacy_office_metadata,
    "xls": _extract_legacy_office_metadata,
    "mp3": _extract_audio_metadata,
    "wav": _extract_audio_metadata,
    "flac": _extract_audio_metadata,
    "ogg": _extract_audio_metadata,
    "aac": _extract_audio_metadata,
    "aiff": _extract_audio_metadata,
    "mp4": _extract_video_metadata,
    "mov": _extract_video_metadata,
    "avi": _extract_video_metadata,
    "mkv": _extract_video_metadata,
    "webm": _extract_video_metadata,
}


def extract_metadata(file_entry: FileEntry) -> FileMetadata:
    """
    Extract all available metadata from a file.

    Always returns at minimum os.stat metadata.
    Format-specific metadata is best-effort with a 5-second timeout.

    Args:
        file_entry: The FileEntry to extract metadata from.

    Returns:
        FileMetadata with all available fields populated.
    """
    file_path = file_entry.path

    # Always get OS metadata
    os_meta = _extract_os_metadata(file_path)

    # Try format-specific extraction with timeout
    ext = file_entry.extension.lower()
    extractor = EXTRACTORS.get(ext)

    format_meta = {}
    if extractor:
        format_meta = _with_timeout(
            lambda: extractor(file_path),
            timeout=5.0,
            default={},
        ) or {}

    # Merge: format-specific overrides OS where both exist
    merged = {**os_meta, **format_meta}

    # Build FileMetadata, only passing fields it accepts
    valid_fields = set(FileMetadata.model_fields.keys())
    filtered = {k: v for k, v in merged.items() if k in valid_fields and v is not None}

    return FileMetadata(**filtered)
