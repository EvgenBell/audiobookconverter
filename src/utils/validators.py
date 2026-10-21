"""
Validators for AudioBookConverter.
"""
import os
import re
from pathlib import Path
from typing import Tuple, Optional

from core.models import BookInfo, OutputSettings
from i18n.translator import tr


def validate_output_folder(folder: str) -> Tuple[bool, str]:
    """
    Validate an output folder path.
    Returns (is_valid, error_message).
    """
    if not folder:
        return False, tr("errors.no_output_folder")

    path = Path(folder)

    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return False, f"Cannot create folder: {e}"

    if not path.is_dir():
        return False, "Path is not a directory"

    if not os.access(path, os.W_OK):
        return False, "No write permission for folder"

    return True, ""


def validate_filename(filename: str) -> Tuple[bool, str]:
    """
    Validate a filename for invalid characters.
    Returns (is_valid, error_message).
    """
    if not filename:
        return False, "Filename cannot be empty"

    # Check for invalid characters on Windows
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        if char in filename:
            return False, tr("errors.invalid_filename")

    # Check for reserved names on Windows
    reserved = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    }

    stem = filename.split(".", 1)[0].rstrip(" ").upper()
    if stem in reserved:
        return False, f"'{stem}' is a reserved filename"

    # Check for control characters
    if any(ord(c) < 32 for c in filename):
        return False, "Filename contains invalid characters"
    if filename.endswith((" ", ".")):
        return False, "Filename cannot end with a space or dot"

    # Check length (Windows MAX_PATH is 260, but be conservative)
    if len(filename) > 200:
        return False, "Filename is too long"

    return True, ""


def validate_book_info(book_info: BookInfo) -> Tuple[bool, list[str]]:
    """
    Validate book info fields.
    Returns (is_valid, list_of_errors).
    """
    errors = []

    if not book_info.title or not book_info.title.strip():
        errors.append(tr("errors.missing_title"))

    # Validate year if provided
    if book_info.year:
        current_year = 2026  # Could use datetime.now().year
        if book_info.year < 1800 or book_info.year > current_year + 1:
            errors.append(f"Invalid year: {book_info.year}")

    # Validate book number if provided
    if book_info.book_number < 0:
        errors.append("Book number cannot be negative")

    return len(errors) == 0, errors


def validate_audio_file(file_path: str) -> Tuple[bool, str]:
    """
    Validate an audio file.
    Returns (is_valid, error_message).
    """
    path = Path(file_path)

    if not path.exists():
        return False, f"File not found: {file_path}"

    if not path.is_file():
        return False, f"Not a file: {file_path}"

    # Check extension
    valid_extensions = {".mp3", ".wma", ".m4a", ".flac", ".wav", ".aac", ".ogg", ".m4b", ".mp4"}
    if path.suffix.lower() not in valid_extensions:
        return False, f"Unsupported format: {path.suffix}"

    # Check file is readable
    if not os.access(file_path, os.R_OK):
        return False, f"No read permission: {file_path}"

    # Check file size (minimum reasonable size)
    if path.stat().st_size < 100:
        return False, "File is too small or corrupted"

    return True, ""


def validate_artwork_file(file_path: str) -> Tuple[bool, str]:
    """
    Validate an artwork image file.
    Returns (is_valid, error_message).
    """
    path = Path(file_path)

    if not path.exists():
        return False, f"File not found: {file_path}"

    # Check extension
    valid_extensions = {".jpg", ".jpeg", ".png"}
    if path.suffix.lower() not in valid_extensions:
        return False, "Only JPG and PNG images are supported"

    # Check file size (max ~10MB)
    max_size = 10 * 1024 * 1024
    if path.stat().st_size > max_size:
        return False, "Image file is too large (max 10MB)"

    # Try to verify it's actually an image
    try:
        with open(file_path, "rb") as f:
            header = f.read(8)

        # JPEG starts with FF D8 FF
        if header[:3] == b'\xff\xd8\xff':
            return True, ""

        # PNG starts with 89 50 4E 47
        if header[:4] == b'\x89PNG':
            return True, ""

        return False, "File doesn't appear to be a valid image"

    except Exception as e:
        return False, f"Error reading file: {e}"


def validate_output_settings(settings: OutputSettings) -> Tuple[bool, list[str]]:
    """
    Validate output settings.
    Returns (is_valid, list_of_errors).
    """
    errors = []

    # Validate output folder
    valid, err = validate_output_folder(settings.output_folder)
    if not valid:
        errors.append(err)

    # Validate filename template
    if not settings.filename_template:
        errors.append("Filename template is empty")
    else:
        valid, unknown = validate_template_variables(settings.filename_template)
        if not valid:
            errors.append("Unknown filename variables: " + ", ".join(unknown))

    # Validate bitrate
    valid_bitrates = [32, 48, 64, 80, 96, 112, 128, 144, 160, 192, 224, 256, 320]
    if settings.bitrate not in valid_bitrates:
        errors.append(f"Unusual bitrate: {settings.bitrate}k (common values: 64k-192k)")

    # Validate duration target
    if settings.mode.value == "duration" and settings.duration_target < 5:
        errors.append("Duration target should be at least 5 minutes")

    return len(errors) == 0, errors


def validate_template_variables(template: str) -> Tuple[bool, list[str]]:
    """
    Validate filename template variables.
    Returns (is_valid, list_of_unknown_variables).
    """
    valid_vars = {
        "Writer", "Title", "Narrator", "Series",
        "Book", "Year", "Genre", "Part"
    }

    # Find all variables in template
    pattern = r'\{(\w+)\}'
    found_vars = set(re.findall(pattern, template))

    unknown = found_vars - valid_vars

    return len(unknown) == 0, list(unknown)
