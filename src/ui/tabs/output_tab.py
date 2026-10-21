"""
Output tab for AudioBookConverter.
"""
import os
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QComboBox, QSpinBox,
    QGroupBox, QFileDialog, QLabel, QRadioButton, QButtonGroup
)
from PySide6.QtCore import Signal, Qt, QSignalBlocker

from core.models import OutputSettings, BookInfo, OutputMode, ChannelMode, SampleRate
from i18n.translator import tr


class OutputTab(QWidget):
    """Tab for configuring output settings."""

    settings_changed = Signal()

    BITRATES = [32, 48, 64, 80, 96, 112, 128, 144, 160, 192, 224, 256, 320]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._settings = OutputSettings()
        self._book_info: Optional[BookInfo] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)

        # Output folder group
        folder_group = QGroupBox(tr("output.output_folder"))
        self.folder_group = folder_group
        folder_layout = QHBoxLayout(folder_group)

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText(tr("output.output_folder"))

        self.browse_btn = QPushButton(tr("output.browse"))

        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(self.browse_btn)

        layout.addWidget(folder_group)

        # Filename template group
        template_group = QGroupBox(tr("output.filename_template"))
        self.template_group = template_group
        template_layout = QVBoxLayout(template_group)

        self.template_edit = QLineEdit()
        self.template_edit.setText("{Writer} - {Title} ({Narrator}).m4b")
        template_layout.addWidget(self.template_edit)

        help_label = QLabel(
            tr("output.variables") + " {Writer}, {Title}, {Narrator}, {Series}, {Book}, {Year}, {Genre}, {Part}"
        )
        self.help_label = help_label
        help_label.setObjectName("muted")
        help_label.setWordWrap(True)
        template_layout.addWidget(help_label)

        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setTextFormat(Qt.PlainText)
        self.preview_label.setObjectName("preview")

        template_layout.addWidget(self.preview_label)

        layout.addWidget(template_group)

        # Audio settings group
        audio_group = QGroupBox(tr("output.audio_settings"))
        audio_layout = QFormLayout(audio_group)
        self.audio_group = audio_group
        self.audio_layout = audio_layout

        self.bitrate_combo = QComboBox()
        self.bitrate_combo.setEditable(False)
        for br in self.BITRATES:
            self.bitrate_combo.addItem(f"{br} kbps", br)
        self.bitrate_combo.setCurrentText("96 kbps")
        audio_layout.addRow(tr("output.bitrate") + ":", self.bitrate_combo)

        self.channels_combo = QComboBox()
        self.channels_combo.addItem(tr("output.auto"), "auto")
        self.channels_combo.addItem(tr("output.mono"), "mono")
        self.channels_combo.addItem(tr("output.stereo"), "stereo")
        audio_layout.addRow(tr("output.channels") + ":", self.channels_combo)

        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItem(tr("output.auto"), "auto")
        self.sample_rate_combo.addItem("44100 Hz", "44100")
        self.sample_rate_combo.addItem("48000 Hz", "48000")
        audio_layout.addRow(tr("output.sample_rate") + ":", self.sample_rate_combo)

        layout.addWidget(audio_group)

        # Output mode group
        mode_group = QGroupBox(tr("output.mode"))
        self.mode_group = mode_group
        mode_layout = QVBoxLayout(mode_group)

        self.mode_buttons = QButtonGroup(self)

        self.single_radio = QRadioButton(tr("output.single_m4b"))
        self.single_radio.setChecked(True)
        self.mode_buttons.addButton(self.single_radio, 0)
        mode_layout.addWidget(self.single_radio)

        self.split_parts_radio = QRadioButton(tr("output.split_by_parts"))
        self.mode_buttons.addButton(self.split_parts_radio, 2)
        mode_layout.addWidget(self.split_parts_radio)

        self.split_duration_radio = QRadioButton(tr("output.split_by_duration"))
        self.mode_buttons.addButton(self.split_duration_radio, 1)
        mode_layout.addWidget(self.split_duration_radio)

        # Duration target
        duration_layout = QHBoxLayout()
        self.duration_label = QLabel(tr("output.duration_target") + ":")
        self.duration_spin = QSpinBox()
        self.duration_spin.setMinimum(5)
        self.duration_spin.setMaximum(600)
        self.duration_spin.setValue(60)
        self.duration_spin.setSuffix(" " + tr("output.minutes"))
        self.duration_spin.setEnabled(False)

        duration_layout.addWidget(self.duration_label)
        duration_layout.addWidget(self.duration_spin)
        duration_layout.addStretch()

        mode_layout.addLayout(duration_layout)

        layout.addWidget(mode_group)

        layout.addStretch()

    def retranslate_ui(self) -> None:
        with QSignalBlocker(self):
            for group, key in ((self.folder_group, "output_folder"), (self.template_group, "filename_template"),
                               (self.audio_group, "audio_settings"), (self.mode_group, "mode")):
                group.setTitle(tr(f"output.{key}"))
            self.folder_edit.setPlaceholderText(tr("output.output_folder"))
            self.browse_btn.setText(tr("output.browse"))
            self.help_label.setText(tr("output.variables") + " {Writer}, {Title}, {Narrator}, {Series}, {Book}, {Year}, {Genre}, {Part}")
            for widget, key in ((self.bitrate_combo, "bitrate"), (self.channels_combo, "channels"),
                                (self.sample_rate_combo, "sample_rate")):
                self.audio_layout.labelForField(widget).setText(tr(f"output.{key}") + ":")
            for index, key in enumerate(("auto", "mono", "stereo")):
                self.channels_combo.setItemText(index, tr(f"output.{key}"))
            self.sample_rate_combo.setItemText(0, tr("output.auto"))
            for widget, key in ((self.single_radio, "single_m4b"), (self.split_parts_radio, "split_by_parts"),
                                (self.split_duration_radio, "split_by_duration")):
                widget.setText(tr(f"output.{key}"))
            self.duration_label.setText(tr("output.duration_target") + ":")
            self.duration_spin.setSuffix(" " + tr("output.minutes"))
            self._update_preview()

    def _connect_signals(self) -> None:
        """Connect signals."""
        self.browse_btn.clicked.connect(self._browse_folder)
        self.folder_edit.textChanged.connect(self._on_change)
        self.template_edit.textChanged.connect(self._on_change)
        self.bitrate_combo.currentTextChanged.connect(self._on_change)
        self.channels_combo.currentIndexChanged.connect(self._on_change)
        self.sample_rate_combo.currentIndexChanged.connect(self._on_change)
        self.mode_buttons.buttonClicked.connect(self._on_mode_change)
        self.duration_spin.valueChanged.connect(self._on_change)

    def _browse_folder(self) -> None:
        """Browse for output folder."""
        folder = QFileDialog.getExistingDirectory(
            self,
            tr("dialogs.select_folder"),
            self.folder_edit.text()
        )

        if folder:
            self.folder_edit.setText(folder)

    def _on_change(self) -> None:
        """Handle setting changes."""
        self._update_preview()
        self.settings_changed.emit()

    def _on_mode_change(self) -> None:
        """Handle output mode change."""
        is_duration = self.split_duration_radio.isChecked()
        self.duration_spin.setEnabled(is_duration)
        self._on_change()

    def _update_preview(self) -> None:
        """Update the filename preview."""
        if self._book_info:
            settings = self.get_settings()
            filename = settings.get_output_filename(self._book_info, 1 if settings.mode != OutputMode.SINGLE_M4B else 0)
            self.preview_label.setText(filename)
        else:
            self.preview_label.setText(tr("book_info.output_name_preview"))

    def get_settings(self) -> OutputSettings:
        """Get the current output settings."""
        bitrate_text = self.bitrate_combo.currentText()
        try:
            bitrate = int(bitrate_text.split()[0])
        except (ValueError, IndexError):
            bitrate = 96

        if self.split_duration_radio.isChecked():
            mode = OutputMode.SPLIT_BY_DURATION
        elif self.split_parts_radio.isChecked():
            mode = OutputMode.SPLIT_BY_PARTS
        else:
            mode = OutputMode.SINGLE_M4B

        return OutputSettings(
            output_folder=self.folder_edit.text(),
            filename_template=self.template_edit.text(),
            bitrate=bitrate,
            channels=ChannelMode(self.channels_combo.currentData()),
            sample_rate=SampleRate(self.sample_rate_combo.currentData()),
            mode=mode,
            duration_target=self.duration_spin.value()
        )

    def set_settings(self, settings: OutputSettings) -> None:
        """Set the output settings."""
        self._settings = settings

        self.blockSignals(True)

        self.folder_edit.setText(settings.output_folder)
        self.template_edit.setText(settings.filename_template)

        bitrate_text = f"{settings.bitrate} kbps"
        index = self.bitrate_combo.findText(bitrate_text)
        if index >= 0:
            self.bitrate_combo.setCurrentIndex(index)
        else:
            self.bitrate_combo.setEditText(bitrate_text)

        channel_index = self.channels_combo.findData(settings.channels.value)
        if channel_index >= 0:
            self.channels_combo.setCurrentIndex(channel_index)

        sr_index = self.sample_rate_combo.findData(settings.sample_rate.value)
        if sr_index >= 0:
            self.sample_rate_combo.setCurrentIndex(sr_index)

        if settings.mode == OutputMode.SPLIT_BY_DURATION:
            self.split_duration_radio.setChecked(True)
        elif settings.mode == OutputMode.SPLIT_BY_PARTS:
            self.split_parts_radio.setChecked(True)
        else:
            self.single_radio.setChecked(True)

        self.duration_spin.setValue(settings.duration_target)
        self.duration_spin.setEnabled(settings.mode == OutputMode.SPLIT_BY_DURATION)

        self.blockSignals(False)

        self._update_preview()

    def update_preview(self, book_info: BookInfo) -> None:
        """Update the filename preview with book info."""
        self._book_info = book_info
        self._update_preview()

    def clear(self) -> None:
        """Clear all settings."""
        self.blockSignals(True)

        self.folder_edit.clear()
        self.template_edit.setText("{Writer} - {Title} ({Narrator}).m4b")
        self.bitrate_combo.setCurrentText("96 kbps")
        self.channels_combo.setCurrentIndex(0)
        self.sample_rate_combo.setCurrentIndex(0)
        self.single_radio.setChecked(True)
        self.duration_spin.setValue(60)

        self.blockSignals(False)
        
