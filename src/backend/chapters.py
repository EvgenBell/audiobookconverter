"""
Chapter handling for AudioBookConverter.
Includes smart parsing for chapter names from filenames and folders.
"""
import re
import math
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from core.models import AudioFile, Chapter


@dataclass
class ParsedChapter:
    """Result of parsing a filename for chapter info."""
    part_number: int = 0
    chapter_number: int = 0
    track_number: int = 0
    title: str = ""
    details: str = ""
    original_filename: str = ""


class ChapterParser:
    """Smart parser for chapter names from filenames and folder structures."""

    PART_KEYWORDS = {
        "en": ["part", "book", "volume", "vol"],
        "ru": ["часть", "книга", "том"]
    }

    CHAPTER_KEYWORDS = {
        "en": ["chapter", "ch"],
        "ru": ["глава", "гл"]
    }

    def __init__(self, language: str = "en"):
        self.language = language

    def parse_filename(self, filename: str, folder_name: str = "") -> ParsedChapter:
        """Parse a filename to extract part/chapter information."""
        result = ParsedChapter(original_filename=filename)
        basename = Path(filename).stem
        result.details = basename

        patterns = [
            self._pattern_part_chapter_track,
            self._pattern_chapter_keyword,
            self._pattern_part_keyword,
            self._pattern_numeric_chapter,
            self._pattern_leading_number,
        ]

        for pattern_func in patterns:
            if pattern_func(basename, result):
                break

        if result.part_number == 0 and folder_name:
            self._parse_folder_for_part(folder_name, result)

        if not result.title:
            result.title = self._generate_title(result, basename)

        return result

    def _pattern_part_chapter_track(self, basename: str, result: ParsedChapter) -> bool:
        """Match patterns like 'Часть 2_10-01' or 'Part 2_10-01'."""
        pattern_ru = r"(часть|книга|том)\s*(\d+)[_\s-]+(\d+)(?:[-_](\d+))?"
        match = re.search(pattern_ru, basename, re.IGNORECASE)

        if match:
            result.part_number = int(match.group(2))
            result.chapter_number = int(match.group(3))
            if match.group(4):
                result.track_number = int(match.group(4))
            return True

        pattern_en = r"(part|book|volume|vol\.?)[\s_-]*(\d+)[_\s-]+(\d+)(?:[-_](\d+))?"
        match = re.search(pattern_en, basename, re.IGNORECASE)

        if match:
            result.part_number = int(match.group(2))
            result.chapter_number = int(match.group(3))
            if match.group(4):
                result.track_number = int(match.group(4))
            return True

        return False

    def _pattern_chapter_keyword(self, basename: str, result: ParsedChapter) -> bool:
        """Match patterns like 'Chapter 5' or 'Глава 3'."""
        pattern_ru = r"(глава|гл\.?)\s*[._-]?\s*(\d+)"
        match = re.search(pattern_ru, basename, re.IGNORECASE)

        if match:
            result.chapter_number = int(match.group(2))
            after_match = basename[match.end():].strip(" -_:")
            if after_match:
                result.title = after_match
            return True

        pattern_en = r"(chapter|ch\.?)\s*[._-]?\s*(\d+)"
        match = re.search(pattern_en, basename, re.IGNORECASE)

        if match:
            result.chapter_number = int(match.group(2))
            after_match = basename[match.end():].strip(" -_:")
            if after_match:
                result.title = after_match
            return True

        return False

    def _pattern_part_keyword(self, basename: str, result: ParsedChapter) -> bool:
        """Match patterns like 'Part 2' or 'Часть 2'."""
        pattern_ru = r"(часть|книга|том)\s*[._-]?\s*(\d+)"
        match = re.search(pattern_ru, basename, re.IGNORECASE)

        if match:
            result.part_number = int(match.group(2))
            after_match = basename[match.end():].strip(" -_:")
            if after_match:
                result.title = after_match
            return True

        pattern_en = r"(part|book|vol\.?|volume)\s*[._-]?\s*(\d+)"
        match = re.search(pattern_en, basename, re.IGNORECASE)

        if match:
            result.part_number = int(match.group(2))
            after_match = basename[match.end():].strip(" -_:")
            if after_match:
                result.title = after_match
            return True

        return False

    def _pattern_numeric_chapter(self, basename: str, result: ParsedChapter) -> bool:
        """Match patterns like '02_THE_MAGUS' or '10-Chapter Name'."""
        pattern = r"^(\d{1,3})[\s_\-\.]+(.+)$"
        match = re.match(pattern, basename)

        if match:
            num = int(match.group(1))
            title = match.group(2).strip()

            result.chapter_number = num
            result.title = self._clean_title(title)

            return True

        return False

    def _pattern_leading_number(self, basename: str, result: ParsedChapter) -> bool:
        """Match patterns with just leading numbers like '1 Title' or '01 Title'."""
        pattern = r"^(\d{1,3})\s+(.+)$"
        match = re.match(pattern, basename)

        if match:
            result.chapter_number = int(match.group(1))
            result.title = self._clean_title(match.group(2))
            return True

        return False

    def _parse_folder_for_part(self, folder_name: str, result: ParsedChapter) -> None:
        """Extract part info from folder name."""
        pattern_ru = r"(часть|книга|том)\s*[._-]?\s*(\d+)"
        match = re.search(pattern_ru, folder_name, re.IGNORECASE)

        if match:
            result.part_number = int(match.group(2))
            return

        pattern_en = r"(part|book|vol\.?|volume)\s*[._-]?\s*(\d+)"
        match = re.search(pattern_en, folder_name, re.IGNORECASE)

        if match:
            result.part_number = int(match.group(2))

    def _clean_title(self, title: str) -> str:
        """Clean up a title string."""
        title = title.replace("_", " ")
        title = " ".join(title.split())
        if "." in title and title.rsplit(".", 1)[1].lower() in ("mp3", "m4a", "flac", "wav", "ogg", "aac"):
            title = title.rsplit(".", 1)[0]
        return title.strip()

    def _generate_title(self, result: ParsedChapter, basename: str) -> str:
        """Generate a title from parsed info."""
        parts = []

        if result.part_number > 0:
            part_word = "Part" if self.language == "en" else "Часть"
            parts.append(f"{part_word} {result.part_number}")

        if result.chapter_number > 0:
            chapter_word = "Chapter" if self.language == "en" else "Глава"
            parts.append(f"{chapter_word} {result.chapter_number}")

        if parts:
            return " – ".join(parts)

        return self._clean_title(basename)


class ChapterManager:
    """Manages chapter operations for a project."""

    def __init__(self, language: str = "en"):
        self.parser = ChapterParser(language)

    def auto_generate_chapters(
        self,
        audio_files: list[AudioFile],
        parse_filenames: bool = True
    ) -> list[Chapter]:
        """
        Automatically generate chapters from a list of audio files.
        Each file becomes one chapter with English title for iOS compatibility.
        """
        chapters = []
        current_time = 0.0

        for i, audio_file in enumerate(audio_files):
            end_time = current_time + audio_file.duration

            title = f"Chapter {i + 1:02d}"
            parsed = self.parser.parse_filename(audio_file.filename, Path(audio_file.path).parent.name) if parse_filenames else None
            if parsed:
                title = parsed.title
            
            # Store filename stem in details for reference
            file_stem = Path(audio_file.path).stem

            chapter = Chapter(
                title=title,
                start_time=current_time,
                end_time=end_time,
                details=file_stem,
                part_number=parsed.part_number or 1 if parsed else 1,
                chapter_number=parsed.chapter_number or i + 1 if parsed else i + 1,
                original_filename=audio_file.filename,
                source_file_index=i
            )

            chapters.append(chapter)
            current_time = end_time

        return chapters

    def combine_chapters(self, chapters: list[Chapter], indices: list[int]) -> Chapter:
        """Combine consecutive chapters into one."""
        if not indices:
            return chapters[0]

        indices = sorted(indices)

        first = chapters[indices[0]]
        last = chapters[indices[-1]]

        combined = Chapter(
            title=first.title,
            start_time=first.start_time,
            end_time=last.end_time,
            details=", ".join(chapters[i].title for i in indices),
            part_number=first.part_number,
            chapter_number=first.chapter_number,
            original_filename="",
            source_file_index=first.source_file_index
        )

        return combined

    def split_chapter(
        self,
        chapter: Chapter,
        split_time: float
    ) -> tuple[Chapter, Chapter]:
        """Split a chapter at a given timestamp."""
        if split_time <= 0 or split_time >= chapter.duration:
            return chapter, chapter

        absolute_split = chapter.start_time + split_time

        first = Chapter(
            title=f"{chapter.title} (1)",
            start_time=chapter.start_time,
            end_time=absolute_split,
            part_number=chapter.part_number,
            chapter_number=chapter.chapter_number,
            original_filename=chapter.original_filename,
            source_file_index=chapter.source_file_index
        )

        second = Chapter(
            title=f"{chapter.title} (2)",
            start_time=absolute_split,
            end_time=chapter.end_time,
            part_number=chapter.part_number,
            chapter_number=chapter.chapter_number,
            original_filename=chapter.original_filename,
            source_file_index=chapter.source_file_index
        )

        return first, second

    def rename_chapter(self, chapter: Chapter, new_title: str) -> Chapter:
        """Rename a chapter."""
        chapter.title = new_title
        return chapter

    def get_chapters_by_part(self, chapters: list[Chapter]) -> dict[int, list[Chapter]]:
        """Group chapters by part number."""
        parts: dict[int, list[Chapter]] = {}

        for chapter in chapters:
            if chapter.part_number not in parts:
                parts[chapter.part_number] = []
            parts[chapter.part_number].append(chapter)

        return parts

    def recalculate_times(self, chapters: list[Chapter], audio_files: list[AudioFile]) -> list[Chapter]:
        """Recalculate chapter times based on current audio file order."""
        current_time = 0.0

        for i, chapter in enumerate(chapters):
            if i < len(audio_files):
                chapter.start_time = current_time
                chapter.end_time = current_time + audio_files[i].duration
                current_time = chapter.end_time

        return chapters

    def validate_chapters(self, chapters: list[Chapter], total_duration: float) -> list[str]:
        """Validate chapters and return list of issues."""
        issues = []

        if not chapters:
            issues.append("No chapters defined")
            return issues

        for i in range(len(chapters) - 1):
            if abs(chapters[i].end_time - chapters[i + 1].start_time) > 0.1:
                issues.append(f"Gap between '{chapters[i].title}' and '{chapters[i + 1].title}'")

        if chapters[0].start_time > 0.1:
            issues.append("First chapter doesn't start at the beginning")

        if abs(chapters[-1].end_time - total_duration) > 0.1:
            issues.append("Last chapter doesn't cover the full duration")

        for chapter in chapters:
            if not (math.isfinite(chapter.start_time) and math.isfinite(chapter.end_time)) or not (
                0 <= chapter.start_time < chapter.end_time <= total_duration + 0.1
            ):
                issues.append(f"Chapter '{chapter.title}' has invalid timestamps")

        return issues


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:d}:{secs:02d}"


def parse_timestamp(timestamp: str) -> float:
    """Parse a timestamp string (HH:MM:SS or MM:SS) to seconds."""
    parts = timestamp.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError("Invalid timestamp")
    values = [float(part) for part in parts]
    if any(not math.isfinite(value) or value < 0 for value in values) or any(
        value >= 60 for value in values[1:]
    ) or any(not value.is_integer() for value in values[:-1]):
        raise ValueError("Invalid timestamp")
    result = 0.0
    for value in values:
        result = result * 60 + value
    return result
        
