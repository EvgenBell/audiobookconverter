"""
Project file I/O for AudioBookConverter.
Handles saving and loading .abcproj files.
"""
import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

from .models import (
    AudioFile, Chapter, BookInfo, OutputSettings, Artwork, AppSettings
)


# Current schema version for project files
SCHEMA_VERSION = "1.0"
APP_VERSION = "1.1.0"


class Project:
    """Represents a complete AudioBookConverter project."""

    def __init__(self):
        self.file_path: str = ""
        self.modified: bool = False

        # Project data
        self.input_files: list[AudioFile] = []
        self.book_info: BookInfo = BookInfo()
        self.output_settings: OutputSettings = OutputSettings()
        self.artwork: Optional[Artwork] = None
        self.chapters: list[Chapter] = []

        # Metadata
        self.schema_version: str = SCHEMA_VERSION
        self.app_version: str = APP_VERSION
        self.created: str = datetime.now().isoformat()
        self.modified_time: str = self.created

    def mark_modified(self) -> None:
        """Mark the project as modified."""
        self.modified = True
        self.modified_time = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """Serialize the project to a dictionary."""
        return {
            "schema_version": self.schema_version,
            "app_version": self.app_version,
            "created": self.created,
            "modified": self.modified_time,
            "input_files": [f.to_dict() for f in self.input_files],
            "book_info": self.book_info.to_dict(),
            "output_settings": self.output_settings.to_dict(),
            "artwork": self.artwork.to_dict() if self.artwork else None,
            "chapters": [c.to_dict() for c in self.chapters]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        """Deserialize a project from a dictionary."""
        project = cls()
        project.schema_version = data.get("schema_version", "1.0")
        project.app_version = data.get("app_version", "1.0.0")
        project.created = data.get("created", datetime.now().isoformat())
        project.modified_time = data.get("modified", datetime.now().isoformat())
        project.input_files = [AudioFile.from_dict(f) for f in data.get("input_files", [])]
        project.book_info = BookInfo.from_dict(data.get("book_info", {}))
        project.output_settings = OutputSettings.from_dict(data.get("output_settings", {}))

        artwork_data = data.get("artwork")
        if artwork_data:
            project.artwork = Artwork.from_dict(artwork_data)

        project.chapters = [Chapter.from_dict(c) for c in data.get("chapters", [])]
        project.modified = False

        return project

    def save(self, file_path: str) -> None:
        """Save the project to a file."""
        self.modified_time = datetime.now().isoformat()
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=Path(file_path).resolve().parent,
                                             delete=False, encoding="utf-8") as f:
                temp_path = f.name
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, file_path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
        self.file_path = file_path
        self.modified = False

    @classmethod
    def load(cls, file_path: str) -> "Project":
        """Load a project from a file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        project = cls.from_dict(data)
        project.file_path = file_path
        return project

    def validate_files(self) -> Tuple[list[str], list[str]]:
        """
        Check if all input files still exist.
        Returns (valid_paths, missing_paths).
        """
        valid = []
        missing = []

        for audio_file in self.input_files:
            if Path(audio_file.path).exists():
                valid.append(audio_file.path)
            else:
                missing.append(audio_file.path)

        return valid, missing

    def relink_files(self, search_folder: str) -> int:
        """
        Attempt to relink missing files by searching in a folder.
        Returns the number of files successfully relinked.
        """
        search_path = Path(search_folder)
        relinked = 0

        for audio_file in self.input_files:
            if not Path(audio_file.path).exists():
                # Try to find by filename in search folder
                filename = Path(audio_file.path).name

                for found_file in search_path.rglob(filename):
                    audio_file.path = str(found_file)
                    relinked += 1
                    break

        return relinked

    def get_total_duration(self) -> float:
        """Calculate total duration of all input files."""
        return sum(f.duration for f in self.input_files)

    def clear(self) -> None:
        """Clear all project data."""
        self.input_files.clear()
        self.chapters.clear()
        self.book_info = BookInfo()
        self.output_settings = OutputSettings()
        self.artwork = None
        self.file_path = ""
        self.modified = False


def migrate_project(data: dict) -> dict:
    """
    Migrate an older project schema to the current version.
    This ensures backward compatibility.
    """
    schema = data.get("schema_version", "1.0")

    # Future migrations would go here
    # if schema == "1.0":
    #     data = migrate_1_0_to_1_1(data)
    # if schema == "1.1":
    #     data = migrate_1_1_to_1_2(data)

    data["schema_version"] = SCHEMA_VERSION
    return data
