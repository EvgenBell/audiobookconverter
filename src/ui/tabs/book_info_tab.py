"""
Book Info tab for AudioBookConverter.
"""
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QSpinBox, QComboBox, QTextEdit, QLabel, QGroupBox
)
from PySide6.QtCore import Signal, Qt, QSignalBlocker

from core.models import BookInfo
from i18n.translator import tr


class BookInfoTab(QWidget):
    """Tab for editing book metadata."""

    info_changed = Signal()

    GENRES = [
        "audiobook", "fiction", "non_fiction", "science_fiction",
        "fantasy", "mystery", "romance", "thriller", "biography",
        "history", "self_help", "educational"
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)

        # Book Info group
        info_group = QGroupBox(tr("tabs.book_info"))
        form_layout = QFormLayout(info_group)
        self.info_group = info_group
        self.form_layout = form_layout

        # Title
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(tr("book_info.title"))
        form_layout.addRow(tr("book_info.title") + ":", self.title_edit)

        # Writer
        self.writer_edit = QLineEdit()
        self.writer_edit.setPlaceholderText(tr("book_info.writer"))
        form_layout.addRow(tr("book_info.writer") + ":", self.writer_edit)

        # Narrator
        self.narrator_edit = QLineEdit()
        self.narrator_edit.setPlaceholderText(tr("book_info.narrator"))
        form_layout.addRow(tr("book_info.narrator") + ":", self.narrator_edit)

        # Genre
        self.genre_combo = QComboBox()
        self.genre_combo.setEditable(True)
        self._populate_genres()
        form_layout.addRow(tr("book_info.genre") + ":", self.genre_combo)

        # Series
        self.series_edit = QLineEdit()
        self.series_edit.setPlaceholderText(tr("book_info.series"))
        form_layout.addRow(tr("book_info.series") + ":", self.series_edit)

        # Book Number
        self.book_num_spin = QSpinBox()
        self.book_num_spin.setMinimum(0)
        self.book_num_spin.setMaximum(999)
        self.book_num_spin.setSpecialValueText("-")
        form_layout.addRow(tr("book_info.book_number") + ":", self.book_num_spin)

        # Year
        self.year_spin = QSpinBox()
        self.year_spin.setMinimum(0)
        self.year_spin.setMaximum(2100)
        self.year_spin.setSpecialValueText("-")
        self.year_spin.setValue(0)
        form_layout.addRow(tr("book_info.year") + ":", self.year_spin)

        # Comment
        self.comment_edit = QTextEdit()
        self.comment_edit.setMaximumHeight(80)
        self.comment_edit.setPlaceholderText(tr("book_info.comment"))
        form_layout.addRow(tr("book_info.comment") + ":", self.comment_edit)

        layout.addWidget(info_group)

        # Output preview group
        preview_group = QGroupBox(tr("book_info.output_name_preview"))
        self.preview_group = preview_group
        preview_layout = QVBoxLayout(preview_group)

        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setTextFormat(Qt.PlainText)
        self.preview_label.setObjectName("preview")

        preview_layout.addWidget(self.preview_label)

        layout.addWidget(preview_group)

        # Add stretch at bottom
        layout.addStretch()

    def retranslate_ui(self) -> None:
        self.info_group.setTitle(tr("tabs.book_info"))
        self.preview_group.setTitle(tr("book_info.output_name_preview"))
        for widget, key in (
            (self.title_edit, "title"), (self.writer_edit, "writer"),
            (self.narrator_edit, "narrator"), (self.genre_combo, "genre"),
            (self.series_edit, "series"), (self.book_num_spin, "book_number"),
            (self.year_spin, "year"), (self.comment_edit, "comment"),
        ):
            text = tr(f"book_info.{key}")
            self.form_layout.labelForField(widget).setText(text + ":")
            if isinstance(widget, (QLineEdit, QTextEdit)):
                widget.setPlaceholderText(text)
        # Genre is book metadata: translate the suggestions without changing its value.
        genre = self.genre_combo.currentText()
        with QSignalBlocker(self.genre_combo):
            for index, key in enumerate(self.GENRES):
                self.genre_combo.setItemText(index, tr(f"genre.{key}"))
            self.genre_combo.setEditText(genre)

    def _populate_genres(self) -> None:
        """Populate the genre dropdown."""
        for genre_key in self.GENRES:
            genre_name = tr(f"genre.{genre_key}")
            self.genre_combo.addItem(genre_name, genre_key)

        # Set default
        self.genre_combo.setCurrentText(tr("genre.audiobook"))

    def _connect_signals(self) -> None:
        """Connect signals."""
        self.title_edit.textChanged.connect(self.info_changed)
        self.writer_edit.textChanged.connect(self.info_changed)
        self.narrator_edit.textChanged.connect(self.info_changed)
        self.genre_combo.currentTextChanged.connect(self.info_changed)
        self.series_edit.textChanged.connect(self.info_changed)
        self.book_num_spin.valueChanged.connect(self.info_changed)
        self.year_spin.valueChanged.connect(self.info_changed)
        self.comment_edit.textChanged.connect(self.info_changed)

    def get_book_info(self) -> BookInfo:
        """Get the current book info."""
        year = self.year_spin.value()
        book_num = self.book_num_spin.value()

        return BookInfo(
            title=self.title_edit.text().strip(),
            writer=self.writer_edit.text().strip(),
            narrator=self.narrator_edit.text().strip(),
            genre=self.genre_combo.currentText(),
            series=self.series_edit.text().strip(),
            book_number=book_num if book_num > 0 else 0,
            year=year if year > 0 else 0,
            comment=self.comment_edit.toPlainText().strip()
        )

    def set_book_info(self, info: BookInfo) -> None:
        """Set the book info fields."""
        # Block signals temporarily
        self.blockSignals(True)

        self.title_edit.setText(info.title)
        self.writer_edit.setText(info.writer)
        self.narrator_edit.setText(info.narrator)
        self.genre_combo.setCurrentText(info.genre)
        self.series_edit.setText(info.series)
        self.book_num_spin.setValue(info.book_number)
        self.year_spin.setValue(info.year)
        self.comment_edit.setPlainText(info.comment)

        self.blockSignals(False)

    def update_preview(self, filename: str) -> None:
        """Update the output filename preview."""
        self.preview_label.setText(filename)

    def clear(self) -> None:
        """Clear all fields."""
        self.blockSignals(True)

        self.title_edit.clear()
        self.writer_edit.clear()
        self.narrator_edit.clear()
        self.genre_combo.setCurrentText(tr("genre.audiobook"))
        self.series_edit.clear()
        self.book_num_spin.setValue(0)
        self.year_spin.setValue(0)
        self.comment_edit.clear()

        self.blockSignals(False)
