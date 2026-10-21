"""
Path utilities for AudioBookConverter.
"""
import os
import sys
from pathlib import Path
from typing import Optional


def get_app_dir() -> Path:
    """Get the application data directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", "~"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"

    return base / "AudioBookConverter"


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_app_dir() / "config.json"


def get_log_path() -> Path:
    """Get the log file path."""
    return get_app_dir() / "audiobookconverter.log"


def ensure_app_dir() -> Path:
    """Ensure the application directory exists and return it."""
    app_dir = get_app_dir()
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_default_output_folder() -> str:
    """Get the default output folder for converted files."""
    # Try user's Music folder first
    music = Path.home() / "Music" / "Audiobooks"
    if music.parent.exists():
        music.mkdir(parents=True, exist_ok=True)
        return str(music)

    # Fallback to Documents
    docs = Path.home() / "Documents" / "Audiobooks"
    docs.mkdir(parents=True, exist_ok=True)
    return str(docs)


def is_valid_output_path(path: str) -> bool:
    """Check if a path is valid for output."""
    if not path:
        return False

    try:
        p = Path(path)
        # Check if parent directory exists or can be created
        if p.parent.exists():
            return True
        p.parent.mkdir(parents=True, exist_ok=True)
        return True
    except (OSError, ValueError):
        return False


def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from a filename."""
    invalid_chars = '<>:"/\\|?*'

    for char in invalid_chars:
        filename = filename.replace(char, "_")

    # Remove control characters
    filename = "".join(c for c in filename if ord(c) >= 32)

    # Remove leading/trailing spaces and dots
    filename = filename.strip(" .")

    # Don't allow empty filenames
    if not filename:
        filename = "Untitled"

    return filename


def get_unique_filename(folder: str, filename: str) -> str:
    """Get a unique filename in a folder, adding (2), (3), etc. if needed."""
    path = Path(folder) / filename

    if not path.exists():
        return filename

    stem = path.stem
    suffix = path.suffix
    counter = 2

    while True:
        new_filename = f"{stem} ({counter}){suffix}"
        new_path = Path(folder) / new_filename

        if not new_path.exists():
            return new_filename

        counter += 1


def format_file_size(size_bytes: int) -> str:
    """Format a file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def get_file_icon_path() -> Optional[str]:
    """Get the path to the application icon file."""
    # Check common locations
    locations = [
        Path(__file__).parent.parent.parent / "resources" / "icon.ico",
        Path(__file__).parent.parent.parent / "icon.ico",
        Path(__file__).parent.parent.parent.parent / "icon.ico",
    ]

    for loc in locations:
        if loc.exists():
            return str(loc)

    return None
