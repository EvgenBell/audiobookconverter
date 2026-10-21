"""
FFmpeg backend for AudioBookConverter.
Handles file probing, encoding, and conversion operations.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import threading
import sys
import math
from pathlib import Path
from typing import Optional, Tuple, Callable
from dataclasses import dataclass

from core.models import AudioFile, OutputSettings, ChannelMode, SampleRate


@dataclass
class FFmpegInfo:
    """Information about FFmpeg installation."""
    ffmpeg_path: str = ""
    ffprobe_path: str = ""
    version: str = ""
    available: bool = False


class FFmpegBackend:
    """Backend for FFmpeg operations."""

    SUPPORTED_FORMATS = {".mp3", ".wma", ".m4a", ".flac", ".wav", ".aac", ".ogg", ".m4b", ".mp4"}

    def __init__(self, ffmpeg_path: str = "", ffprobe_path: str = ""):
        self._ffmpeg_path = ffmpeg_path
        self._ffprobe_path = ffprobe_path
        self._process: Optional[subprocess.Popen] = None
        self._decoder: Optional[subprocess.Popen] = None
        self._cancelled = threading.Event()
        self._resumed = threading.Event()
        self._resumed.set()
        self._process_lock = threading.Lock()

    @property
    def ffmpeg_path(self) -> str:
        if self._ffmpeg_path and os.path.isfile(self._ffmpeg_path):
            return self._ffmpeg_path
        return self._find_executable("ffmpeg")

    @property
    def ffprobe_path(self) -> str:
        if self._ffprobe_path and os.path.isfile(self._ffprobe_path):
            return self._ffprobe_path
        return self._find_executable("ffprobe")

    @staticmethod
    def _find_executable(name: str) -> str:
        """Find an executable in PATH or common locations."""
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
        for folder in (root / "bin", root, Path(sys.executable).parent):
            candidate = folder / (name + (".exe" if os.name == "nt" else ""))
            if candidate.is_file():
                return str(candidate)
        path = shutil.which(name)
        if path:
            return path

        common_paths = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.environ.get("LocalAppData", ""),
            os.path.expanduser("~\\ffmpeg\\bin"),
            "C:\\ffmpeg\\bin",
        ]

        for base in common_paths:
            if not base:
                continue
            exe_path = os.path.join(base, f"{name}.exe")
            if os.path.isfile(exe_path):
                return exe_path
            exe_path = os.path.join(base, "ffmpeg", "bin", f"{name}.exe")
            if os.path.exists(exe_path):
                return exe_path
            exe_path = os.path.join(base, "bin", f"{name}.exe")
            if os.path.exists(exe_path):
                return exe_path

        return ""

    def check_available(self) -> FFmpegInfo:
        """Check if FFmpeg and FFprobe are available."""
        info = FFmpegInfo()

        ffmpeg = self.ffmpeg_path
        ffprobe = self.ffprobe_path

        if ffmpeg and os.path.exists(ffmpeg):
            info.ffmpeg_path = ffmpeg
            try:
                result = subprocess.run(
                    [ffmpeg, "-version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                )
                if result.returncode == 0:
                    match = re.search(r"ffmpeg version (\S+)", result.stdout)
                    if match:
                        info.version = match.group(1)
            except Exception:
                pass

        if ffprobe and os.path.exists(ffprobe):
            info.ffprobe_path = ffprobe

        info.available = bool(info.version and info.ffprobe_path)
        return info

    def probe_file(self, file_path: str) -> Optional[AudioFile]:
        """Get metadata about an audio file using ffprobe."""
        ffprobe = self.ffprobe_path

        if not ffprobe or not os.path.exists(ffprobe):
            print(f"ffprobe not found: {ffprobe}")
            return None

        if not file_path or not os.path.exists(file_path):
            print(f"Audio file not found: {file_path}")
            return None

        try:
            cmd = [
                ffprobe,
                "-v", "error",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path
            ]

            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                creationflags=creation_flags
            )

            if result.returncode != 0:
                print(
                    f"ffprobe failed for {file_path}\n"
                    f"Return code: {result.returncode}\n"
                    f"STDERR: {result.stderr}\n"
                    f"STDOUT: {result.stdout}"
                )
                return None

            if not result.stdout.strip():
                print(f"ffprobe returned empty output for {file_path}")
                return None

            data = json.loads(result.stdout)

            # Prefer the default audio track; ties keep the first audio stream.
            audio_stream = max(
                (stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"),
                key=lambda stream: stream.get("disposition", {}).get("default", 0),
                default=None
            )

            if not audio_stream:
                print(f"No audio stream found in {file_path}")
                return None

            format_info = data.get("format", {}) or {}

            def safe_float(value, default: float = 0.0) -> float:
                try:
                    if value in (None, "", "N/A"):
                        return default
                    number = float(value)
                    return number if math.isfinite(number) else default
                except (TypeError, ValueError, OverflowError):
                    return default

            def safe_int(value, default: int = 0) -> int:
                try:
                    if value in (None, "", "N/A"):
                        return default
                    return int(float(value))
                except (TypeError, ValueError):
                    return default

            duration = safe_float(
                audio_stream.get("duration")
            ) or safe_float(format_info.get("duration"))
            if duration <= 0:
                return None

            file_size = safe_int(format_info.get("size") or 0)

            sample_rate = safe_int(audio_stream.get("sample_rate") or 0)
            channels = safe_int(audio_stream.get("channels") or 0)

            bitrate = safe_int(
                audio_stream.get("bit_rate")
                or format_info.get("bit_rate")
                or 0
            )

            audio_file = AudioFile(
                path=file_path,
                duration=duration,
                file_size=file_size,
                sample_rate=sample_rate,
                channels=channels,
                codec=audio_stream.get("codec_name", "") or "",
                bitrate=bitrate,
                audio_stream_index=audio_stream["index"]
            )

            return audio_file

        except Exception as e:
            print(f"Error probing {file_path}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def probe_multiple(self, file_paths: list[str]) -> list[AudioFile]:
        """Probe multiple files."""
        results = []
        for path in file_paths:
            audio_file = self.probe_file(path)
            if audio_file:
                results.append(audio_file)
        return results

    def cancel(self) -> None:
        """Stop owned processes; the conversion thread closes and reaps them."""
        self._cancelled.set()
        self._resumed.set()
        with self._process_lock:
            for process in (self._decoder, self._process):
                if process is not None and process.poll() is None:
                    process.kill()

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._resumed.clear()
        else:
            self._resumed.set()

    def wait_until_resumed(self) -> bool:
        self._resumed.wait()
        return not self._cancelled.is_set()

    def _parse_progress_data(self, data: dict, total_duration: float, expected_size: float = 0) -> Optional[float]:
        """Parse progress from -progress pipe:1 output."""
        # Try numeric time keys (may differ between ffmpeg builds)
        for key, div in (
            ("out_time_us", 1_000_000),  # microseconds
            ("out_time_ms", 1_000_000),  # often microseconds despite name
            ("out_time_ns", 1_000_000_000),  # nanoseconds
        ):
            v = data.get(key, "")
            if v and v != "N/A":
                try:
                    current_time = int(v) / div
                    if total_duration > 0:
                        return min(100.0, (current_time / total_duration) * 100.0)
                except ValueError:
                    pass

        # Fallback: parse out_time=HH:MM:SS.micro
        out_time = data.get("out_time", "")
        if out_time and out_time != "N/A":
            m = re.search(r"(\d+):(\d+):(\d+\.?\d*)", out_time)
            if m:
                h = float(m.group(1))
                mi = float(m.group(2))
                s = float(m.group(3))
                current_time = h * 3600 + mi * 60 + s
                if total_duration > 0:
                    return min(100.0, (current_time / total_duration) * 100.0)

        # Fallback: use total_size if time is N/A (common with concat demuxer)
        total_size = data.get("total_size", "")
        if total_size and total_size != "N/A" and expected_size > 0:
            try:
                current_size = int(total_size)
                return min(100.0, (current_size / expected_size) * 100.0)
            except ValueError:
                pass

        return None

    def concat_and_encode(
        self,
        input_files: list[AudioFile],
        output_path: str,
        settings: OutputSettings,
        progress_callback: Optional[Callable[[float, float], None]] = None,
        chapters: list = None,
        start_time: float = 0.0,
        duration: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """Stream decoded PCM into one AAC encoder, including chapters in the first pass.

        Decoding each source separately also supports mixed codecs, rates and layouts.
        Pipes provide backpressure: memory use is independent of the book's length.
        """
        total = sum(f.duration for f in input_files)
        duration = total - start_time if duration is None else duration
        if not input_files or not math.isfinite(total) or not all(
            math.isfinite(f.duration) and f.duration > 0 for f in input_files
        ):
            return False, "Invalid input duration"
        if not math.isfinite(start_time) or not math.isfinite(duration) or not (
            0 <= start_time < total and 0 < duration <= total - start_time + 0.001
        ):
            return False, "Invalid output interval"
        if not self.ffmpeg_path:
            return False, "FFmpeg not found"
        if not self.wait_until_resumed():
            return False, "Cancelled"

        rate = (int(settings.sample_rate.value) if settings.sample_rate != SampleRate.AUTO
                else (48000 if max(f.sample_rate for f in input_files) >= 48000 else 44100))
        channels = (1 if settings.channels == ChannelMode.MONO else 2
                    if settings.channels == ChannelMode.STEREO else
                    min(2, max(1, max(f.channels for f in input_files))))
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        metadata_file = None
        feeder = None
        feed_errors = []
        process = None
        succeeded = False
        try:
            metadata_file = self._create_chapters_metadata(chapters) if chapters else None
            with tempfile.TemporaryFile() as errors:
                cmd = [self.ffmpeg_path, "-y", "-nostdin", "-v", "error",
                       "-progress", "pipe:1", "-nostats", "-f", "f32le",
                       "-ar", str(rate), "-ac", str(channels), "-i", "pipe:0"]
                if metadata_file:
                    cmd += ["-f", "ffmetadata", "-i", metadata_file]
                cmd += ["-map", "0:a:0", "-map_metadata", "1" if metadata_file else "-1",
                        "-map_chapters", "1" if metadata_file else "-1",
                        "-c:a", "aac", "-b:a", f"{settings.bitrate}k",
                        "-aac_coder", "fast", "-f", "mp4", "-movflags", "+faststart", output_path]
                with self._process_lock:
                    if self._cancelled.is_set():
                        return False, "Cancelled"
                    process = self._process = subprocess.Popen(
                        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=errors, creationflags=flags)

                def feed_audio():
                    offset = 0.0
                    try:
                        for audio_file in input_files:
                            begin = max(0.0, start_time - offset)
                            end = min(audio_file.duration, start_time + duration - offset)
                            offset += audio_file.duration
                            if end <= begin:
                                continue
                            if not self.wait_until_resumed():
                                break
                            with tempfile.TemporaryFile() as decoder_errors:
                                stream = f"0:{audio_file.audio_stream_index}" if audio_file.audio_stream_index is not None else "0:a:0"
                                cmd = [self.ffmpeg_path, "-nostdin", "-v", "error", "-xerror",
                                       "-ss", str(begin), "-i", os.path.abspath(audio_file.path),
                                       "-t", str(end - begin), "-map", stream, "-vn",
                                       "-ar", str(rate), "-ac", str(channels),
                                       "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"]
                                with self._process_lock:
                                    if self._cancelled.is_set():
                                        break
                                    decoder = self._decoder = subprocess.Popen(
                                        cmd, stdout=subprocess.PIPE, stderr=decoder_errors,
                                        creationflags=flags)
                                try:
                                    while self.wait_until_resumed():
                                        chunk = decoder.stdout.read(65536)
                                        if not chunk:
                                            break
                                        process.stdin.write(chunk)
                                    if self._cancelled.is_set():
                                        break
                                    if decoder.wait() != 0:
                                        decoder_errors.seek(0)
                                        raise RuntimeError(decoder_errors.read().decode("utf-8", "replace")[-2000:])
                                finally:
                                    if decoder.poll() is None:
                                        decoder.kill()
                                    decoder.wait()
                                    decoder.stdout.close()
                                    with self._process_lock:
                                        self._decoder = None
                    except Exception as exc:
                        feed_errors.append(str(exc))
                    finally:
                        try:
                            process.stdin.close()
                        except OSError:
                            pass

                feeder = threading.Thread(target=feed_audio)
                feeder.start()
                started = time.monotonic()
                data = {}
                for raw in process.stdout:
                    key, _, value = raw.decode("utf-8", "replace").strip().partition("=")
                    data[key] = value
                    if key == "progress" and progress_callback and self._resumed.is_set():
                        percent = self._parse_progress_data(data, duration)
                        if percent is not None:
                            percent = max(0.0, min(99.0, percent))
                            elapsed = time.monotonic() - started
                            eta = elapsed * (100 - percent) / percent if percent > 0 else 0
                            progress_callback(percent, eta)
                        data.clear()
                process.wait()
                if process.returncode != 0:
                    # Unblock a paused feeder if the encoder failed independently.
                    self._resumed.set()
                feeder.join()
                if self._cancelled.is_set():
                    return False, "Cancelled"
                if process.returncode != 0 or feed_errors:
                    errors.seek(0)
                    error = errors.read().decode("utf-8", "replace")[-2000:]
                    return False, error or "\n".join(feed_errors) or "FFmpeg failed"
                if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
                    return False, "Output file is empty or missing"
                succeeded = True
                if progress_callback:
                    progress_callback(100.0, 0.0)
                return True, ""
        except Exception as exc:
            return False, str(exc)
        finally:
            if not succeeded and process is not None:
                self.cancel()
            if feeder is not None:
                feeder.join()
            if process is not None:
                process.wait()
                process.stdout.close()
            with self._process_lock:
                self._process = None
            if metadata_file:
                os.unlink(metadata_file)

    def _create_chapters_metadata(self, chapters: list) -> str:
        """Write UTF-8 FFmetadata with escaped chapter titles."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ffmeta", delete=False, encoding="utf-8", newline="\n") as f:
            f.write(";FFMETADATA1\n")
            for chapter in chapters:
                title = re.sub(r"([\\=;#\n])", r"\\\1", chapter.title.replace("\r", ""))
                f.write(f"\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={round(chapter.start_time * 1000)}\n")
                f.write(f"END={round(chapter.end_time * 1000)}\ntitle={title}\n")
            return f.name

    def extract_m4b_info(self, m4b_path: str, extract_artwork: bool = True) -> Tuple[dict, list, Optional[str]]:
        """Extract metadata, chapters, and artwork from an M4B file."""
        metadata = {}
        chapters = []
        artwork_path = None

        if not self.ffprobe_path:
            return metadata, chapters, artwork_path

        try:
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                "-show_chapters",
                m4b_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                timeout=60
            )

            if result.returncode != 0:
                return metadata, chapters, artwork_path

            data = json.loads(result.stdout)
            format_info = data.get("format", {})
            tags = format_info.get("tags", {})

            metadata = {
                "title": tags.get("title", ""),
                "writer": tags.get("artist", tags.get("author", "")),
                "narrator": tags.get("narrator", tags.get("performer", "")),
                "genre": tags.get("genre", "Audiobook"),
                "year": tags.get("date", tags.get("year", "")),
                "comment": tags.get("comment", tags.get("description", "")),
                "duration": float(format_info.get("duration", 0)),
            }

            for ch in data.get("chapters", []):
                chapters.append({
                    "id": ch.get("id", 0),
                    "title": ch.get("tags", {}).get("title", f"Chapter {ch.get('id', 0)}"),
                    "start_time": float(ch.get("start_time", 0)),
                    "end_time": float(ch.get("end_time", 0)),
                })

            for stream in data.get("streams", []):
                if extract_artwork and stream.get("codec_name") in ("mjpeg", "png", "bmp"):
                    artwork_path = self._extract_artwork(m4b_path, stream.get("index", 0))
                    break

            return metadata, chapters, artwork_path

        except Exception as e:
            print(f"Error extracting M4B info: {e}")
            return metadata, chapters, artwork_path

    def _extract_artwork(self, m4b_path: str, stream_index: int) -> Optional[str]:
        """Extract embedded artwork from an M4B file."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                output_path = f.name

            cmd = [
                self.ffmpeg_path,
                "-y",
                "-nostdin",
                "-i", m4b_path,
                "-map", f"0:{stream_index}",
                "-vframes", "1",
                output_path
            ]

            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=60,
                creationflags=creation_flags
            )

            if result.returncode == 0 and os.path.exists(output_path):
                return output_path

        except Exception as e:
            print(f"Error extracting artwork: {e}")

        return None


# Global instance
_backend_instance: Optional[FFmpegBackend] = None


def get_backend() -> FFmpegBackend:
    """Get the global FFmpeg backend instance."""
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = FFmpegBackend()
    return _backend_instance


def set_ffmpeg_paths(ffmpeg_path: str = "", ffprobe_path: str = "") -> None:
    """Set custom FFmpeg/FFprobe paths."""
    global _backend_instance

    if ffmpeg_path and not ffprobe_path:
        folder = os.path.dirname(ffmpeg_path)
        candidate = os.path.join(folder, "ffprobe.exe")
        if os.path.exists(candidate):
            ffprobe_path = candidate

    _backend_instance = FFmpegBackend(ffmpeg_path, ffprobe_path)
