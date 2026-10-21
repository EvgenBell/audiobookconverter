"""
File list widget for AudioBookConverter.
"""
from typing import Optional
from pathlib import Path
import re
import os
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QAbstractItemView, QMessageBox, QLabel, QProgressBar, QStyle
)
from PySide6.QtCore import Qt, Signal, QThread, QEvent, QItemSelectionModel
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from core.models import AudioFile
from backend.ffmpeg import get_backend
from backend.chapters import format_duration
from i18n.translator import tr


class ProbeWorker(QThread):
    progress = Signal(int, int)

    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent)
        self.paths = paths
        self.files = []
        self.failed = []
        self.backend = get_backend()

    def run(self) -> None:
        # A small bounded pool overlaps process startup and disk I/O without flooding the OS.
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = pool.map(lambda path: None if self.isInterruptionRequested() else self.backend.probe_file(path), self.paths)
            for index, (path, audio) in enumerate(zip(self.paths, results), 1):
                if self.isInterruptionRequested():
                    break
                if audio:
                    self.files.append(audio)
                else:
                    self.failed.append(path)
                self.progress.emit(index, len(self.paths))


class FileListWidget(QWidget):
    """Widget for managing the list of input audio files."""

    loading_changed = Signal(bool)
    files_changed = Signal(list)  # Emitted when files are added/removed/reordered

    SUPPORTED_FORMATS = ["*.mp3", "*.wma", "*.m4a", "*.flac", "*.wav", "*.aac", "*.ogg", "*.m4b", "*.mp4"]
    SUPPORTED_SUFFIXES = {ext.replace("*", "").lower() for ext in SUPPORTED_FORMATS}

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._files: list[AudioFile] = []
        self._probe_worker = None

        self._setup_ui()
        self._connect_signals()

        # Enable drag and drop
        self.setAcceptDrops(True)

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header_layout = QHBoxLayout()

        self.label = QLabel(tr("main.files_label"))
        self.label.setObjectName("sectionTitle")
        header_layout.addWidget(self.label)

        layout.addLayout(header_layout)

        # File table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "#", tr("chapters.name"), tr("chapters.duration"), tr("chapters.details")
        ])

        # Configure table
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.setDragDropMode(QAbstractItemView.DragDrop)
        self.table.setDragDropOverwriteMode(False)
        self.table.setDefaultDropAction(Qt.MoveAction)
        self.table.viewport().installEventFilter(self)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        self.empty_label = QLabel(tr("main.drop_hint"), self.table.viewport())
        self.empty_label.setObjectName("emptyState")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.table)
        self.import_progress = QProgressBar()
        self.import_progress.hide()
        layout.addWidget(self.import_progress)

        # Button row
        btn_layout = QHBoxLayout()

        self.add_btn = QPushButton(tr("main.add_files"))
        self.add_folder_btn = QPushButton(tr("main.add_folder"))
        self.remove_btn = QPushButton(tr("main.remove"))
        self.clear_btn = QPushButton(tr("main.clear"))

        self.add_btn.setProperty("primary", True)
        self.add_folder_btn.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
        self.remove_btn.setEnabled(False)

        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.add_folder_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(self.clear_btn)

        layout.addLayout(btn_layout)

        # Second button row
        btn_layout2 = QHBoxLayout()

        self.up_btn = QPushButton(tr("main.move_up"))
        self.down_btn = QPushButton(tr("main.move_down"))

        self.up_btn.setEnabled(False)
        self.down_btn.setEnabled(False)

        btn_layout2.addWidget(self.up_btn)
        btn_layout2.addWidget(self.down_btn)

        layout.addLayout(btn_layout2)

    def retranslate_ui(self) -> None:
        for widget, key in (
            (self.label, "files_label"), (self.empty_label, "drop_hint"),
            (self.add_btn, "add_files"), (self.add_folder_btn, "add_folder"),
            (self.remove_btn, "remove"), (self.clear_btn, "clear"),
            (self.up_btn, "move_up"), (self.down_btn, "move_down"),
        ):
            widget.setText(tr(f"main.{key}"))
        self.table.setHorizontalHeaderLabels([
            "#", tr("chapters.name"), tr("chapters.duration"), tr("chapters.details")
        ])
        if self.is_loading:
            self._on_probe_progress(self.import_progress.value(), self.import_progress.maximum())

    def _connect_signals(self) -> None:
        """Connect UI signals."""
        self.add_btn.clicked.connect(self._add_files)
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn.clicked.connect(self._clear_files)
        self.up_btn.clicked.connect(self._move_up)
        self.down_btn.clicked.connect(self._move_down)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)

    def _add_files(self) -> None:
        """Open file dialog to add files."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            tr("dialogs.select_audio_files"),
            "",
            f"Audio / MP4 ({' '.join(self.SUPPORTED_FORMATS)})"
        )

        if files:
            self._add_file_paths(files)

    def _add_folder(self) -> None:
        """Open folder dialog and add all supported audio files from it."""
        folder = QFileDialog.getExistingDirectory(
            self,
            tr("dialogs.select_folder"),
            ""
        )

        if not folder:
            return

        paths = self._collect_audio_files_from_folder(folder, recursive=False)
        if not paths:
            QMessageBox.information(
                self,
                tr("main.add_folder"),
                tr("main.no_supported_files")
            )
            return

        self._add_file_paths(paths)

    def _collect_audio_files_from_folder(self, folder: str, recursive: bool = False) -> list[str]:
        """Collect supported audio files from folder."""
        root = Path(folder)
        iterator = root.rglob("*") if recursive else root.iterdir()

        paths = [
            str(path)
            for path in iterator
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES
        ]

        return self._sort_paths_naturally(paths)

    def _sort_paths_naturally(self, paths: list[str]) -> list[str]:
        """Sort paths as 1.mp3, 2.mp3, 10.mp3 instead of 1.mp3, 10.mp3, 2.mp3."""
        def key(value: str):
            name = Path(value).name.lower()
            return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]

        return sorted(paths, key=key)

    def _is_supported_audio_path(self, path: str) -> bool:
        """Check if path has supported audio extension."""
        return Path(path).suffix.lower() in self.SUPPORTED_SUFFIXES

    @property
    def is_loading(self) -> bool:
        return self._probe_worker is not None

    def _add_file_paths(self, paths: list[str]) -> None:
        if self.is_loading:
            return
        seen = {os.path.normcase(os.path.abspath(f.path)) for f in self._files}
        unique = []
        for path in self._sort_paths_naturally(paths):
            path = os.path.abspath(path)
            key = os.path.normcase(path)
            if key not in seen and Path(path).is_file() and self._is_supported_audio_path(path):
                seen.add(key)
                unique.append(path)
        if not unique:
            return
        self._probe_worker = ProbeWorker(unique, self)
        self._probe_worker.progress.connect(self._on_probe_progress)
        self._probe_worker.finished.connect(self._on_probe_finished)
        self.import_progress.setRange(0, len(unique))
        self.import_progress.setValue(0)
        self.import_progress.show()
        self.setEnabled(False)
        self.loading_changed.emit(True)
        self._probe_worker.start()

    def _on_probe_progress(self, count: int, total: int) -> None:
        self.import_progress.setValue(count)
        self.import_progress.setFormat(tr("main.reading_files", count=count, total=total))

    def _on_probe_finished(self) -> None:
        worker = self._probe_worker
        self._probe_worker = None
        self.setEnabled(True)
        self.import_progress.hide()
        if worker.files:
            self._files.extend(worker.files)
            self._update_table()
            self.files_changed.emit(self._files)
        if worker.failed and not worker.isInterruptionRequested():
            QMessageBox.warning(self, tr("app.title"), tr("main.read_failed") + "\n\n" + "\n".join(worker.failed[:10]))
        worker.deleteLater()
        self.loading_changed.emit(False)

    def _remove_selected(self) -> None:
        """Remove selected files."""
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)

        for row in rows:
            if 0 <= row < len(self._files):
                del self._files[row]

        self._update_table()
        self.files_changed.emit(self._files)

    def _clear_files(self) -> None:
        """Clear all files."""
        if self._files:
            reply = QMessageBox.question(
                self,
                tr("main.clear"),
                tr("main.clear_confirm"),
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self._files.clear()
                self._update_table()
                self.files_changed.emit(self._files)

    def _select_rows(self, rows: list[int]) -> None:
        selection = self.table.selectionModel()
        for row in rows:
            selection.select(self.table.model().index(row, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        if rows:
            self.table.setCurrentCell(rows[0], 0, QItemSelectionModel.NoUpdate)
        self._on_selection_changed()

    def _move_up(self) -> None:
        rows = sorted(index.row() for index in self.table.selectionModel().selectedRows())
        if not rows or rows[0] == 0:
            return
        for row in rows:
            self._files[row - 1], self._files[row] = self._files[row], self._files[row - 1]
        self._update_table()
        self._select_rows([row - 1 for row in rows])
        self.files_changed.emit(self._files)

    def _move_down(self) -> None:
        rows = sorted(index.row() for index in self.table.selectionModel().selectedRows())
        if not rows or rows[-1] == len(self._files) - 1:
            return
        for row in reversed(rows):
            self._files[row + 1], self._files[row] = self._files[row], self._files[row + 1]
        self._update_table()
        self._select_rows([row + 1 for row in rows])
        self.files_changed.emit(self._files)

    def _on_selection_changed(self) -> None:
        """Handle selection changes."""
        has_selection = len(self.table.selectedItems()) > 0
        row = self.table.currentRow()

        self.remove_btn.setEnabled(has_selection)
        self.up_btn.setEnabled(has_selection and row > 0)
        self.down_btn.setEnabled(has_selection and 0 <= row < len(self._files) - 1)

    def _move_rows(self, rows: list[int], target: int) -> None:
        selected = set(rows)
        moved = [f for i, f in enumerate(self._files) if i in selected]
        remaining = [f for i, f in enumerate(self._files) if i not in selected]
        target -= sum(row < target for row in rows)
        self._files = remaining[:target] + moved + remaining[target:]
        self._update_table()
        self._select_rows(list(range(target, target + len(moved))))
        self.files_changed.emit(self._files)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.table.viewport():
            kind = event.type()
            if kind == QEvent.Resize:
                self.empty_label.setGeometry(self.table.viewport().rect().adjusted(28, 20, -28, -20))
            elif kind in (QEvent.DragEnter, QEvent.DragMove):
                if event.mimeData().hasUrls() or event.source() is self.table:
                    event.acceptProposedAction()
                    return True
            elif kind == QEvent.Drop:
                if event.mimeData().hasUrls():
                    self.dropEvent(event)
                    return True
                if event.source() is self.table:
                    pos = event.position().toPoint()
                    index = self.table.indexAt(pos)
                    target = index.row() if index.isValid() else len(self._files)
                    if index.isValid() and pos.y() > self.table.visualRect(index).center().y():
                        target += 1
                    rows = [index.row() for index in self.table.selectionModel().selectedRows()]
                    self._move_rows(rows, target)
                    event.accept()
                    return True
        return super().eventFilter(watched, event)

    def _update_table(self) -> None:
        """Update the table display."""
        self.table.setUpdatesEnabled(False)
        self.table.clearSelection()
        self.table.setRowCount(len(self._files))
        self.empty_label.setVisible(not self._files)

        for i, audio_file in enumerate(self._files):
            # Number
            num_item = QTableWidgetItem(str(i + 1))
            num_item.setFlags(num_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, num_item)

            # Name
            name_item = QTableWidgetItem(audio_file.filename)
            name_item.setData(Qt.UserRole, audio_file.path)
            name_item.setToolTip(audio_file.path)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 1, name_item)

            # Duration
            dur_item = QTableWidgetItem(format_duration(audio_file.duration))
            dur_item.setFlags(dur_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 2, dur_item)

            # Details (path)
            path_item = QTableWidgetItem(f"{audio_file.codec.upper()} · {audio_file.sample_rate / 1000:g} kHz")
            path_item.setToolTip(audio_file.path)
            path_item.setFlags(path_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 3, path_item)

        self.table.setUpdatesEnabled(True)
        self._on_selection_changed()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            # Check if any dropped item is a supported audio file or a folder.
            for url in event.mimeData().urls():
                path = Path(url.toLocalFile())
                if path.is_dir() or (path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop event."""
        files = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                files.extend(self._collect_audio_files_from_folder(str(path), recursive=False))
            elif path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES:
                files.append(str(path))

        if files:
            self._add_file_paths(files)
            event.acceptProposedAction()

    def get_files(self) -> list[AudioFile]:
        """Get the current file list."""
        return self._files.copy()

    def set_files(self, files: list[AudioFile]) -> None:
        """Set the file list."""
        self._files = files.copy()
        self._update_table()

    def clear(self) -> None:
        """Clear all files."""
        self._files.clear()
        self._update_table()
