"""
Chapters Editor dialog for AudioBookConverter.
"""
from typing import Optional
from copy import deepcopy

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTreeWidget, QTreeWidgetItem, QLabel, QLineEdit,
    QGroupBox, QCheckBox, QSpinBox, QDialogButtonBox,
    QMessageBox, QWidget, QSplitter, QHeaderView
)
from PySide6.QtCore import Qt

from core.models import AudioFile, Chapter
from backend.chapters import ChapterManager, format_duration, parse_timestamp
from i18n.translator import tr


class ChaptersDialog(QDialog):
    """Dialog for editing chapters."""

    def __init__(
        self,
        audio_files: list[AudioFile],
        chapters: list[Chapter],
        language: str = "en",
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        self._audio_files = audio_files
        self._chapters = deepcopy(chapters) if chapters else []
        self._language = language
        self._manager = ChapterManager(language)

        self._setup_ui()
        self._connect_signals()

        # Populate tree
        if self._chapters:
            self._populate_tree()
        else:
            self._auto_generate()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        self.setWindowTitle(tr("chapters.title"))
        self.setMinimumSize(900, 600)

        layout = QVBoxLayout(self)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left: Chapter tree
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Tree header
        tree_header = QLabel(f"📑 {tr('chapters.chapters')}")
        left_layout.addWidget(tree_header)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setHeaderLabels([
            "#", tr("chapters.name"), tr("chapters.duration"),
            tr("chapters.start_time"), tr("chapters.details")
        ])

        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 50)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.resizeSection(1, 200)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 80)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.resizeSection(3, 80)
        header.setSectionResizeMode(4, QHeaderView.Stretch)

        left_layout.addWidget(self.tree)

        splitter.addWidget(left_widget)

        # Right: Controls
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Editing group
        edit_group = QGroupBox(tr("chapters.rename"))
        edit_layout = QVBoxLayout(edit_group)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("chapters.name"))
        edit_layout.addWidget(self.name_edit)

        rename_btn = QPushButton(tr("chapters.rename"))
        rename_btn.clicked.connect(self._rename_chapter)
        edit_layout.addWidget(rename_btn)

        right_layout.addWidget(edit_group)

        # Actions group
        actions_group = QGroupBox(tr("chapters.actions"))
        actions_layout = QVBoxLayout(actions_group)

        combine_btn = QPushButton(f"🔗 {tr('chapters.combine')}")
        combine_btn.clicked.connect(self._combine_chapters)
        actions_layout.addWidget(combine_btn)

        split_btn = QPushButton(f"✂ {tr('chapters.split')}")
        split_btn.clicked.connect(self._split_chapter)
        actions_layout.addWidget(split_btn)

        right_layout.addWidget(actions_group)

        # Parsing group
        parse_group = QGroupBox(tr("chapters.parsing_rules"))
        parse_layout = QVBoxLayout(parse_group)

        self.auto_parse_check = QCheckBox(tr("chapters.auto_parse"))
        self.auto_parse_check.setChecked(True)
        parse_layout.addWidget(self.auto_parse_check)

        auto_gen_btn = QPushButton(f"🔄 {tr('chapters.auto_generate')}")
        auto_gen_btn.clicked.connect(self._auto_generate)
        parse_layout.addWidget(auto_gen_btn)

        right_layout.addWidget(parse_group)

        # Preview group
        preview_group = QGroupBox(tr("chapters.preview"))
        preview_layout = QVBoxLayout(preview_group)

        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setObjectName("preview")
        preview_layout.addWidget(self.preview_label)

        right_layout.addWidget(preview_group)

        # Add stretch
        right_layout.addStretch()

        splitter.addWidget(right_widget)

        # Set splitter sizes
        splitter.setSizes([600, 300])

        layout.addWidget(splitter)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_preview()

    def _connect_signals(self) -> None:
        """Connect signals."""
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)

    def _populate_tree(self) -> None:
        """Populate the tree with chapters."""
        self.tree.clear()

        # Group by parts
        parts = self._manager.get_chapters_by_part(self._chapters)

        for part_num in sorted(parts.keys()):
            chapters = parts[part_num]

            # Create part item
            if len(parts) > 1:
                part_item = QTreeWidgetItem()
                part_item.setText(0, "")
                part_item.setText(1, f"{tr('chapters.part')} {part_num}")

                # Calculate part duration
                part_duration = sum(ch.duration for ch in chapters)
                part_item.setText(2, format_duration(part_duration))

                part_item.setData(0, Qt.UserRole, "part")
                part_item.setData(1, Qt.UserRole, part_num)

                self.tree.addTopLevelItem(part_item)
            else:
                part_item = None

            # Add chapters
            for i, chapter in enumerate(chapters):
                ch_item = QTreeWidgetItem()

                ch_item.setText(0, str(chapter.chapter_number or i + 1))
                ch_item.setText(1, chapter.title)
                ch_item.setText(2, format_duration(chapter.duration))
                ch_item.setText(3, format_duration(chapter.start_time))
                ch_item.setText(4, chapter.details)

                ch_item.setData(0, Qt.UserRole, "chapter")
                ch_item.setData(1, Qt.UserRole, id(chapter))

                if part_item:
                    part_item.addChild(ch_item)
                else:
                    self.tree.addTopLevelItem(ch_item)

            if part_item:
                part_item.setExpanded(True)

    def _on_selection_changed(self) -> None:
        """Handle tree selection changes."""
        items = self.tree.selectedItems()

        if len(items) == 1:
            item = items[0]
            if item.data(0, Qt.UserRole) == "chapter":
                name = item.text(1)
                self.name_edit.setText(name)
                self._update_preview_for_item(item)
            else:
                self.name_edit.clear()
                self.preview_label.clear()
        else:
            self.name_edit.clear()

    def _update_preview_for_item(self, item: QTreeWidgetItem) -> None:
        """Update preview for a selected item."""
        name = item.text(1)
        duration = item.text(2)
        start = item.text(3)

        preview = f"{tr('chapters.name')}: {name}\n{tr('chapters.duration')}: {duration}\n{tr('chapters.start_time')}: {start}"
        self.preview_label.setText(preview)

    def _update_preview(self) -> None:
        """Update the chapter preview."""
        total = sum(ch.duration for ch in self._chapters)
        count = len(self._chapters)

        self.preview_label.setText(
            f"{count} {tr('chapters.chapters')}\n"
            f"{tr('chapters.duration')}: {format_duration(total)}"
        )

    def _rename_chapter(self) -> None:
        """Rename the selected chapter."""
        items = self.tree.selectedItems()

        if len(items) != 1:
            return

        item = items[0]
        if item.data(0, Qt.UserRole) != "chapter":
            return

        new_name = self.name_edit.text().strip()
        if not new_name:
            return

        item.setText(1, new_name)

        # Update chapter in list
        ch_id = item.data(1, Qt.UserRole)
        for chapter in self._chapters:
            if id(chapter) == ch_id:
                chapter.title = new_name
                break

    def _combine_chapters(self) -> None:
        """Combine selected chapters into one."""
        items = self.tree.selectedItems()

        # Get only chapter items
        chapter_items = [
            item for item in items
            if item.data(0, Qt.UserRole) == "chapter"
        ]

        if len(chapter_items) < 2:
            QMessageBox.information(
                self,
                tr("chapters.combine"),
                tr("chapters.select_consecutive")
            )
            return

        # Get chapter indices
        indices = []
        for item in chapter_items:
            ch_id = item.data(1, Qt.UserRole)
            for i, ch in enumerate(self._chapters):
                if id(ch) == ch_id:
                    indices.append(i)
                    break

        indices.sort()

        # Check consecutiveness
        for i in range(len(indices) - 1):
            if indices[i + 1] - indices[i] != 1:
                QMessageBox.warning(
                    self,
                    tr("chapters.combine"),
                    tr("chapters.must_be_consecutive")
                )
                return

        # Combine
        combined = self._manager.combine_chapters(self._chapters, indices)

        # Remove old chapters and add combined
        for i in reversed(indices):
            del self._chapters[i]

        self._chapters.insert(indices[0], combined)

        self._populate_tree()
        self._update_preview()

    def _split_chapter(self) -> None:
        """Split the selected chapter."""
        items = self.tree.selectedItems()

        if len(items) != 1:
            QMessageBox.information(
                self,
                tr("chapters.split"),
                tr("chapters.select_one")
            )
            return

        item = items[0]
        if item.data(0, Qt.UserRole) != "chapter":
            return

        # Get chapter
        ch_id = item.data(1, Qt.UserRole)
        chapter = None
        chapter_index = -1

        for i, ch in enumerate(self._chapters):
            if id(ch) == ch_id:
                chapter = ch
                chapter_index = i
                break

        if not chapter:
            return

        # Ask for split time
        from PySide6.QtWidgets import QInputDialog

        time_str, ok = QInputDialog.getText(
            self,
            tr("chapters.split"),
            tr("chapters.split_at") + " (" + tr("chapters.timestamp_formats") + "):"
        )

        if not ok or not time_str:
            return

        try:
            split_time = parse_timestamp(time_str)
        except ValueError:
            QMessageBox.warning(self, tr("chapters.split"), tr("chapters.invalid_timestamp"))
            return

        if split_time <= 0 or split_time >= chapter.duration:
            QMessageBox.warning(
                self,
                tr("chapters.split"),
                tr("chapters.split_range", time=format_duration(chapter.duration))
            )
            return

        # Split
        first, second = self._manager.split_chapter(chapter, split_time)

        # Replace chapter with two new ones
        del self._chapters[chapter_index]
        self._chapters.insert(chapter_index, first)
        self._chapters.insert(chapter_index + 1, second)

        self._populate_tree()
        self._update_preview()

    def _auto_generate(self) -> None:
        """Auto-generate chapters from files."""
        parse = self.auto_parse_check.isChecked()
        self._chapters = self._manager.auto_generate_chapters(
            self._audio_files, parse_filenames=parse
        )
        self._populate_tree()
        self._update_preview()

    def get_chapters(self) -> list[Chapter]:
        """Get the edited chapters."""
        return self._chapters.copy()
