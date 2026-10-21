"""
Core data models for AudioBookConverter.
Defines dataclasses for files, chapters, metadata, and settings.
"""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from utils.paths import sanitize_filename


class OutputMode(Enum):
    SINGLE_M4B = "single"
    SPLIT_BY_PARTS = "parts"
    SPLIT_BY_DURATION = "duration"


class ChannelMode(Enum):
    AUTO = "auto"
    MONO = "mono"
    STEREO = "stereo"


class SampleRate(Enum):
    AUTO = "auto"
    SR_44100 = "44100"
    SR_48000 = "48000"


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AudioFile:
    """Represents an input audio file."""
    path: str
    duration: float = 0.0  # in seconds
    file_size: int = 0
    sample_rate: int = 0
    channels: int = 0
    codec: str = ""
    bitrate: int = 0
    audio_stream_index: Optional[int] = None

    @property
    def filename(self) -> str:
        return Path(self.path).name

    @property
    def extension(self) -> str:
        return Path(self.path).suffix.lower()

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "duration": self.duration,
            "file_size": self.file_size,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "codec": self.codec,
            "bitrate": self.bitrate,
            "audio_stream_index": self.audio_stream_index
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AudioFile":
        return cls(
            path=data["path"],
            duration=data.get("duration", 0.0),
            file_size=data.get("file_size", 0),
            sample_rate=data.get("sample_rate", 0),
            channels=data.get("channels", 0),
            codec=data.get("codec", ""),
            bitrate=data.get("bitrate", 0),
            audio_stream_index=data.get("audio_stream_index")
        )


@dataclass
class Chapter:
    """Represents a chapter in an audiobook."""
    title: str
    start_time: float  # in seconds
    end_time: float  # in seconds
    details: str = ""
    part_number: int = 1
    chapter_number: int = 0
    original_filename: str = ""
    source_file_index: int = -1

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "details": self.details,
            "part_number": self.part_number,
            "chapter_number": self.chapter_number,
            "original_filename": self.original_filename,
            "source_file_index": self.source_file_index
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Chapter":
        return cls(
            title=data["title"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            details=data.get("details", ""),
            part_number=data.get("part_number", 1),
            chapter_number=data.get("chapter_number", 0),
            original_filename=data.get("original_filename", ""),
            source_file_index=data.get("source_file_index", -1)
        )


@dataclass
class BookInfo:
    """Metadata for an audiobook."""
    title: str = ""
    writer: str = ""
    narrator: str = ""
    genre: str = "Audiobook"
    series: str = ""
    book_number: int = 0
    year: int = 0
    comment: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "writer": self.writer,
            "narrator": self.narrator,
            "genre": self.genre,
            "series": self.series,
            "book_number": self.book_number,
            "year": self.year,
            "comment": self.comment
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BookInfo":
        return cls(
            title=data.get("title", ""),
            writer=data.get("writer", ""),
            narrator=data.get("narrator", ""),
            genre=data.get("genre", "Audiobook"),
            series=data.get("series", ""),
            book_number=data.get("book_number", 0),
            year=data.get("year", 0),
            comment=data.get("comment", "")
        )


@dataclass
class OutputSettings:
    """Output configuration for encoding."""
    output_folder: str = ""
    filename_template: str = "{Writer} - {Title} ({Narrator}).m4b"
    bitrate: int = 96  # kbps
    channels: ChannelMode = ChannelMode.AUTO
    sample_rate: SampleRate = SampleRate.AUTO
    mode: OutputMode = OutputMode.SINGLE_M4B
    duration_target: int = 60  # minutes for split by duration

    def get_output_filename(self, book_info: BookInfo, part: int = 0) -> str:
        """Generate output filename from template."""
        filename = self.filename_template

        # Replace placeholders
        replacements = {
            "{Writer}": book_info.writer or "Unknown",
            "{Title}": book_info.title or "Untitled",
            "{Narrator}": book_info.narrator or "Unknown",
            "{Series}": book_info.series or "",
            "{Book}": str(book_info.book_number) if book_info.book_number else "",
            "{Year}": str(book_info.year) if book_info.year else "",
            "{Genre}": book_info.genre,
            "{Part}": str(part) if part > 0 else ""
        }

        for placeholder, value in replacements.items():
            filename = filename.replace(placeholder, value)

        # Clean up the filename
        filename = self._clean_filename(filename)

        # Ensure .m4b extension
        if not filename.lower().endswith(".m4b"):
            filename += ".m4b"

        return filename

    @staticmethod
    def _clean_filename(filename: str) -> str:
        """Remove invalid characters from filename."""
        return sanitize_filename(" ".join(filename.split()))

    def to_dict(self) -> dict:
        return {
            "output_folder": self.output_folder,
            "filename_template": self.filename_template,
            "bitrate": self.bitrate,
            "channels": self.channels.value,
            "sample_rate": self.sample_rate.value,
            "mode": self.mode.value,
            "duration_target": self.duration_target
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OutputSettings":
        return cls(
            output_folder=data.get("output_folder", ""),
            filename_template=data.get("filename_template",
                                       "{Writer} - {Title} ({Narrator}).m4b"),
            bitrate=data.get("bitrate", 96),
            channels=ChannelMode(data.get("channels", "auto")),
            sample_rate=SampleRate(data.get("sample_rate", "auto")),
            mode=OutputMode(data.get("mode", "single")),
            duration_target=data.get("duration_target", 60)
        )


@dataclass
class Artwork:
    """Cover artwork for an audiobook."""
    path: str = ""
    embedded_data: bytes = b""
    mime_type: str = ""
    width: int = 0
    height: int = 0

    @property
    def has_artwork(self) -> bool:
        return bool(self.path) or bool(self.embedded_data)

    def to_dict(self) -> dict:
        import base64
        return {
            "path": self.path,
            "embedded_data": base64.b64encode(self.embedded_data).decode("ascii") if self.embedded_data else "",
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Artwork":
        import base64
        embedded = data.get("embedded_data", "")
        if embedded:
            embedded = base64.b64decode(embedded)
        return cls(
            path=data.get("path", ""),
            embedded_data=embedded if isinstance(embedded, bytes) else b"",
            mime_type=data.get("mime_type", ""),
            width=data.get("width", 0),
            height=data.get("height", 0)
        )


@dataclass
class Job:
    """Represents a conversion job in the queue."""
    id: str
    name: str
    book_info: BookInfo
    output_settings: OutputSettings
    input_files: list[AudioFile] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)
    artwork: Optional[Artwork] = None
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    elapsed_time: float = 0.0
    eta: float = 0.0
    output_path: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "book_info": self.book_info.to_dict(),
            "output_settings": self.output_settings.to_dict(),
            "input_files": [f.to_dict() for f in self.input_files],
            "chapters": [c.to_dict() for c in self.chapters],
            "artwork": self.artwork.to_dict() if self.artwork else None,
            "status": self.status.value,
            "progress": self.progress,
            "elapsed_time": self.elapsed_time,
            "eta": self.eta,
            "output_path": self.output_path,
            "error_message": self.error_message
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        return cls(
            id=data["id"],
            name=data["name"],
            book_info=BookInfo.from_dict(data["book_info"]),
            output_settings=OutputSettings.from_dict(data["output_settings"]),
            input_files=[AudioFile.from_dict(f) for f in data.get("input_files", [])],
            chapters=[Chapter.from_dict(c) for c in data.get("chapters", [])],
            artwork=Artwork.from_dict(data["artwork"]) if data.get("artwork") else None,
            status=JobStatus(data.get("status", "pending")),
            progress=data.get("progress", 0.0),
            elapsed_time=data.get("elapsed_time", 0.0),
            eta=data.get("eta", 0.0),
            output_path=data.get("output_path", ""),
            error_message=data.get("error_message", "")
        )


@dataclass
class AppSettings:
    """Application-wide settings."""
    language: str = "en"
    ffmpeg_path: str = ""
    default_output_folder: str = ""
    default_bitrate: int = 96
    artwork_max_size: int = 1000
    auto_parse_chapters: bool = True
    theme: str = "light"

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "ffmpeg_path": self.ffmpeg_path,
            "default_output_folder": self.default_output_folder,
            "default_bitrate": self.default_bitrate,
            "artwork_max_size": self.artwork_max_size,
            "auto_parse_chapters": self.auto_parse_chapters,
            "theme": self.theme
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        return cls(
            language=data.get("language") if data.get("language") in ("en", "ru") else "en",
            ffmpeg_path=data.get("ffmpeg_path", ""),
            default_output_folder=data.get("default_output_folder", ""),
            default_bitrate=data.get("default_bitrate", 96),
            artwork_max_size=data.get("artwork_max_size", 1000),
            auto_parse_chapters=data.get("auto_parse_chapters", True),
            theme=data.get("theme") if data.get("theme") in ("light", "dark") else "light"
        )
