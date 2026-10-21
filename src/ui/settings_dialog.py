"""
Settings dialog for AudioBookConverter.
"""
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QComboBox, QSpinBox,
    QGroupBox, QDialogButtonBox, QMessageBox, QFileDialog,
    QLabel
)
from PySide6.QtCore import Qt

from core.models import AppSettings
from backend.ffmpeg import FFmpegBackend
from pathlib import Path
from i18n.translator import tr, get_language_name, get_available_languages
from utils.paths import get_default_output_folder


class SettingsDialog(QDialog):
    """Dialog for application settings."""

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)

        self._settings = settings
        self._result_settings: Optional[AppSettings] = None

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        self.setWindowTitle(tr("settings.title"))
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Language group
        lang_group = QGroupBox(tr("settings.appearance"))
        lang_layout = QFormLayout(lang_group)

        self.language_combo = QComboBox()
        for lang in get_available_languages():
            self.language_combo.addItem(get_language_name(lang), lang)

        lang_layout.addRow(tr("settings.language") + ":", self.language_combo)

        self.theme_combo = QComboBox()
        for theme in ("light", "dark"):
            self.theme_combo.addItem(tr(f"settings.{theme}"), theme)
        lang_layout.addRow(tr("settings.theme") + ":", self.theme_combo)
        layout.addWidget(lang_group)

        # FFmpeg group
        ffmpeg_group = QGroupBox(tr("settings.ffmpeg_path"))
        ffmpeg_layout = QVBoxLayout(ffmpeg_group)

        path_layout = QHBoxLayout()
        self.ffmpeg_edit = QLineEdit()
        self.ffmpeg_edit.setPlaceholderText(tr("settings.auto_detect"))

        self.ffmpeg_browse = QPushButton(tr("settings.browse"))

        path_layout.addWidget(self.ffmpeg_edit)
        path_layout.addWidget(self.ffmpeg_browse)

        ffmpeg_layout.addLayout(path_layout)

        # Test button
        self.test_btn = QPushButton(tr("settings.test_ffmpeg"))
        self.test_btn.clicked.connect(self._test_ffmpeg)
        ffmpeg_layout.addWidget(self.test_btn)

        # Status label
        self.ffmpeg_status = QLabel()
        self.ffmpeg_status.setObjectName("muted")
        ffmpeg_layout.addWidget(self.ffmpeg_status)

        layout.addWidget(ffmpeg_group)

        # Defaults group
        defaults_group = QGroupBox(tr("settings.defaults"))
        defaults_layout = QFormLayout(defaults_group)

        # Default output folder
        output_layout = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_browse = QPushButton(tr("settings.browse"))
        output_layout.addWidget(self.output_edit)
        output_layout.addWidget(self.output_browse)
        defaults_layout.addRow(tr("settings.default_output") + ":", output_layout)

        # Default bitrate
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.setEditable(False)
        for br in [32, 48, 64, 80, 96, 112, 128, 160, 192, 256, 320]:
            self.bitrate_combo.addItem(f"{br} kbps", br)
        defaults_layout.addRow(tr("settings.default_bitrate") + ":", self.bitrate_combo)

        # Artwork max size
        self.artwork_spin = QSpinBox()
        self.artwork_spin.setRange(500, 3000)
        self.artwork_spin.setSuffix(" px")
        self.artwork_spin.setSingleStep(100)
        defaults_layout.addRow(tr("settings.artwork_max_size") + ":", self.artwork_spin)

        layout.addWidget(defaults_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Connect signals
        self.ffmpeg_browse.clicked.connect(self._browse_ffmpeg)
        self.output_browse.clicked.connect(self._browse_output)

    def _load_settings(self) -> None:
        """Load settings into UI."""
        # Language
        index = self.language_combo.findData(self._settings.language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self._settings.theme))

        # FFmpeg path
        self.ffmpeg_edit.setText(self._settings.ffmpeg_path)

        # Default output
        self.output_edit.setText(
            self._settings.default_output_folder or get_default_output_folder()
        )

        # Default bitrate
        bitrate_text = f"{self._settings.default_bitrate} kbps"
        index = self.bitrate_combo.findText(bitrate_text)
        if index >= 0:
            self.bitrate_combo.setCurrentIndex(index)
        else:
            self.bitrate_combo.setEditText(bitrate_text)

        # Artwork max size
        self.artwork_spin.setValue(self._settings.artwork_max_size)

        # Check FFmpeg status
        self._update_ffmpeg_status()

    def _browse_ffmpeg(self) -> None:
        """Browse for FFmpeg executable."""
        # Try to find ffmpeg.exe
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("settings.select_ffmpeg"),
            "",
            f"{tr('settings.executables')} (*.exe);;{tr('settings.all_files')} (*)"
        )

        if file_path:
            self.ffmpeg_edit.setText(file_path)
            self._update_ffmpeg_status()

    def _browse_output(self) -> None:
        """Browse for default output folder."""
        folder = QFileDialog.getExistingDirectory(
            self,
            tr("dialogs.select_folder"),
            self.output_edit.text()
        )

        if folder:
            self.output_edit.setText(folder)

    def _test_ffmpeg(self) -> None:
        """Test FFmpeg availability."""
        self._update_ffmpeg_status()

    def _update_ffmpeg_status(self) -> None:
        """Update FFmpeg status label."""
        custom_path = self.ffmpeg_edit.text()
        probe_path = str(Path(custom_path).with_name("ffprobe.exe")) if custom_path else ""
        backend = FFmpegBackend(custom_path, probe_path)
        info = backend.check_available()

        if info.available:
            self.ffmpeg_status.setText(tr("settings.ffmpeg_found", version=info.version))
            self.ffmpeg_status.setObjectName("success")
        else:
            self.ffmpeg_status.setText(tr("settings.ffmpeg_not_found"))
            self.ffmpeg_status.setObjectName("error")
        self.ffmpeg_status.style().unpolish(self.ffmpeg_status)
        self.ffmpeg_status.style().polish(self.ffmpeg_status)

    def _save_and_accept(self) -> None:
        """Save settings and close dialog."""
        # Parse bitrate
        bitrate_text = self.bitrate_combo.currentText()
        try:
            bitrate = int(bitrate_text.split()[0])
        except (ValueError, IndexError):
            bitrate = 96

        self._result_settings = AppSettings(
            language=self.language_combo.currentData(),
            theme=self.theme_combo.currentData(),
            ffmpeg_path=self.ffmpeg_edit.text(),
            default_output_folder=self.output_edit.text(),
            default_bitrate=bitrate,
            artwork_max_size=self.artwork_spin.value(),
            auto_parse_chapters=self._settings.auto_parse_chapters
        )

        self.accept()

    def get_settings(self) -> AppSettings:
        """Get the resulting settings."""
        return self._result_settings or self._settings
