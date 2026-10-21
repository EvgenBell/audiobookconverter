"""
Main application entry point for AudioBookConverter.
"""
import sys
import os
from pathlib import Path

# Add src to path for development
src_path = Path(__file__).parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ui.main_window import MainWindow
from core.project_io import APP_VERSION
from utils.paths import ensure_app_dir
from utils.logging import setup_logging
from i18n.translator import set_language, get_system_language


def self_check() -> bool:
    """
    Perform a self-check to verify the application can run.
    Returns True if all checks pass.
    """
    print("AudioBookConverter Self-Check")
    print("=" * 40)

    # Check Python version
    py_version = sys.version_info
    print(f"Python version: {py_version.major}.{py_version.minor}.{py_version.micro}")

    if py_version < (3, 10):
        print("⚠ Warning: Python 3.10+ recommended")
    else:
        print("✅ Python version OK")

    # Check PySide6
    try:
        from PySide6.QtWidgets import QApplication
        print("✅ PySide6 installed")
    except ImportError:
        print("❌ PySide6 not installed")
        return False

    # Check Mutagen
    try:
        from mutagen.mp4 import MP4
        print("✅ Mutagen installed")
    except ImportError:
        print("⚠ Mutagen not installed (metadata features limited)")

    # Check PIL
    try:
        from PIL import Image
        print("✅ Pillow installed")
    except ImportError:
        print("⚠ Pillow not installed (artwork resizing limited)")

    # Check FFmpeg
    from backend.ffmpeg import get_backend
    backend = get_backend()
    info = backend.check_available()

    if info.available:
        print(f"✅ FFmpeg {info.version} found")
        print(f"   FFmpeg: {info.ffmpeg_path}")
        print(f"   FFprobe: {info.ffprobe_path}")

        # Test probe
        print("\nTesting file probe...")
        test_file = None
        for ext in [".mp3", ".m4a", ".wav"]:
            for path in Path(".").rglob(f"*{ext}"):
                test_file = str(path)
                break
            if test_file:
                break

        if test_file:
            audio = backend.probe_file(test_file)
            if audio:
                print(f"✅ Successfully probed: {Path(test_file).name}")
                print(f"   Duration: {audio.duration:.2f}s")
            else:
                print(f"⚠ Could not probe: {test_file}")
        else:
            print("⚠ No test audio file found")

    else:
        print("⚠ FFmpeg not found in PATH")
        print("   Please install FFmpeg or configure path in Settings")

    print("\n" + "=" * 40)
    print("Self-check complete.")

    return info.available


def main():
    """Main entry point."""
    # Ensure app directory exists
    ensure_app_dir()

    # Set up logging
    setup_logging(log_to_file=True, log_to_console=False)

    # Detect and set language
    lang = get_system_language()
    set_language(lang)

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("AudioBookConverter")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("AudioBookConverter")

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    # Run self-check if --check argument provided
    if "--check" in sys.argv or "-c" in sys.argv:
        sys.exit(0 if self_check() else 1)

    main()
