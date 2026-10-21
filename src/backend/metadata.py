"""
Metadata handling for AudioBookConverter.
Uses Mutagen for M4B tag and artwork operations.
Chapters are written via ffmpeg ffmetadata for best Apple Books compatibility.
"""
import os
from pathlib import Path
from typing import Optional, Tuple, List
from io import BytesIO

try:
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen import File as MutagenFile
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

from core.models import BookInfo, Artwork, Chapter


class MetadataHandler:
    """Handles M4B metadata operations using Mutagen + ffmpeg for chapters."""

    @staticmethod
    def write_metadata(m4b_path: str, book_info: BookInfo) -> bool:
        """Write metadata to an M4B file using Mutagen."""
        if not HAS_MUTAGEN:
            return False

        try:
            mp4 = MP4(m4b_path)

            if book_info.title:
                mp4['\xa9nam'] = book_info.title
                mp4['\xa9alb'] = book_info.title

            if book_info.writer:
                mp4['\xa9ART'] = book_info.writer
                mp4['aART'] = book_info.writer

            if book_info.narrator:
                mp4['desc'] = f"Narrator: {book_info.narrator}"

            genre = book_info.genre or "Audiobook"
            mp4['\xa9gen'] = genre

            if book_info.year:
                mp4['\xa9day'] = str(book_info.year)

            if book_info.comment:
                mp4['\xa9cmt'] = book_info.comment

            mp4['stik'] = [2]
            mp4['pgap'] = [1]
            mp4['\xa9too'] = 'AudioBookConverter'

            if book_info.series:
                series_text = book_info.series
                if book_info.book_number:
                    series_text += f", Book {book_info.book_number}"

                existing_desc = mp4.get('desc', [''])[0]
                if existing_desc:
                    mp4['desc'] = f"{existing_desc}\nSeries: {series_text}"
                else:
                    mp4['desc'] = f"Series: {series_text}"

            mp4.save()
            return True

        except Exception as e:
            print(f"Error writing metadata: {e}")
            return False

    @staticmethod
    def read_metadata(m4b_path: str) -> Optional[BookInfo]:
        """Read metadata from an M4B file."""
        if not HAS_MUTAGEN:
            return None

        try:
            mp4 = MP4(m4b_path)
            book_info = BookInfo()

            book_info.title = mp4.get('\xa9nam', [''])[0]
            if not book_info.title:
                book_info.title = mp4.get('\xa9alb', [''])[0]

            book_info.writer = mp4.get('\xa9ART', [''])[0]
            if not book_info.writer:
                book_info.writer = mp4.get('aART', [''])[0]

            book_info.genre = mp4.get('\xa9gen', ['Audiobook'])[0]

            year_str = mp4.get('\xa9day', [''])[0]
            if year_str:
                try:
                    book_info.year = int(year_str[:4])
                except ValueError:
                    pass

            book_info.comment = mp4.get('\xa9cmt', [''])[0]

            desc = mp4.get('desc', [''])[0]
            if desc:
                if 'Narrator:' in desc:
                    parts = desc.split('Narrator:')
                    if len(parts) > 1:
                        book_info.narrator = parts[1].strip().split('\n')[0].strip()

                if 'Series:' in desc:
                    parts = desc.split('Series:')
                    if len(parts) > 1:
                        series_info = parts[1].strip().split('\n')[0].strip()
                        if ', Book ' in series_info:
                            series_parts = series_info.split(', Book ')
                            book_info.series = series_parts[0].strip()
                            try:
                                book_info.book_number = int(series_parts[1].strip())
                            except ValueError:
                                pass
                        else:
                            book_info.series = series_info

            return book_info

        except Exception as e:
            print(f"Error reading metadata: {e}")
            return None

    @staticmethod
    def write_artwork(m4b_path: str, artwork: Artwork) -> bool:
        """Write cover artwork to an M4B file."""
        if not HAS_MUTAGEN:
            return False

        try:
            mp4 = MP4(m4b_path)

            if 'covr' in mp4:
                del mp4['covr']

            image_data = artwork.embedded_data

            if not image_data and artwork.path and os.path.exists(artwork.path):
                with open(artwork.path, 'rb') as f:
                    image_data = f.read()

            if not image_data:
                return False

            ext = Path(artwork.path).suffix.lower() if artwork.path else ""

            if image_data[:4] == b'\x89PNG':
                cover_format = MP4Cover.FORMAT_PNG
            else:
                cover_format = MP4Cover.FORMAT_JPEG

            cover = MP4Cover(image_data, imageformat=cover_format)
            mp4['covr'] = [cover]

            mp4.save()
            return True

        except Exception as e:
            print(f"Error writing artwork: {e}")
            return False

    @staticmethod
    def extract_artwork(m4b_path: str) -> Optional[Artwork]:
        """Extract artwork from an M4B file."""
        if not HAS_MUTAGEN:
            return None

        try:
            mp4 = MP4(m4b_path)

            if 'covr' not in mp4 or not mp4['covr']:
                return None

            cover = mp4['covr'][0]

            artwork = Artwork(
                embedded_data=bytes(cover),
                mime_type="image/png" if cover.imageformat == MP4Cover.FORMAT_PNG else "image/jpeg"
            )

            return artwork

        except Exception as e:
            print(f"Error extracting artwork: {e}")
            return None


def check_mutagen_available() -> bool:
    """Check if Mutagen is available."""
    return HAS_MUTAGEN
    