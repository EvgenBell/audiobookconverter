"""
Main tab widget for AudioBookConverter.
"""
from typing import Optional

from PySide6.QtWidgets import QTabWidget, QWidget, QScrollArea, QFrame, QLayout
from PySide6.QtCore import Signal, QSignalBlocker, Qt

from core.project_io import Project
from ui.tabs.book_info_tab import BookInfoTab
from ui.tabs.artwork_tab import ArtworkTab
from ui.tabs.output_tab import OutputTab
from ui.tabs.queue_tab import QueueTab
from i18n.translator import tr


class MainTabWidget(QTabWidget):
    """Main tab widget containing Book Info, Artwork, Output, and Queue tabs."""

    project_changed = Signal()

    def __init__(self, project: Project, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.project = project

        self.book_info_tab = BookInfoTab()
        self.artwork_tab = ArtworkTab()
        self.output_tab = OutputTab()
        self.queue_tab = QueueTab()

        for tab, title in ((self.book_info_tab, "book_info"), (self.artwork_tab, "artwork"),
                           (self.output_tab, "output")):
            tab.layout().setSizeConstraint(QLayout.SetMinimumSize)
            scroll = QScrollArea()
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setWidget(tab)
            self.addTab(scroll, tr(f"tabs.{title}"))
        self.addTab(self.queue_tab, tr("tabs.queue"))

        self.book_info_tab.info_changed.connect(self._on_info_changed)
        self.output_tab.settings_changed.connect(self._on_settings_changed)
        self.artwork_tab.artwork_changed.connect(self._on_artwork_changed)

    def retranslate_ui(self) -> None:
        for index, (key, tab) in enumerate((
            ("book_info", self.book_info_tab), ("artwork", self.artwork_tab),
            ("output", self.output_tab), ("queue", self.queue_tab),
        )):
            self.setTabText(index, tr(f"tabs.{key}"))
            tab.retranslate_ui()

    def set_main_window(self, main_window) -> None:
        """Set reference to main window for queue tab."""
        self.queue_tab.set_main_window(main_window)

    def _on_info_changed(self) -> None:
        """Handle book info changes."""
        self.project.book_info = self.book_info_tab.get_book_info()
        self.project.mark_modified()
        self.output_tab.update_preview(self.project.book_info)
        self.book_info_tab.update_preview(self.output_tab.preview_label.text())
        self.project_changed.emit()

    def _on_settings_changed(self) -> None:
        """Handle output settings changes."""
        self.project.output_settings = self.output_tab.get_settings()
        self.project.mark_modified()
        self.book_info_tab.update_preview(self.output_tab.preview_label.text())
        self.project_changed.emit()

    def _on_artwork_changed(self) -> None:
        self.project.artwork = self.artwork_tab.get_artwork()
        self.project.mark_modified()
        self.project_changed.emit()

    def update_from_project(self, project: Project) -> None:
        """Update all tabs from a project."""
        self.project = project

        self.book_info_tab.set_book_info(project.book_info)
        self.output_tab.set_settings(project.output_settings)

        with QSignalBlocker(self.artwork_tab):
            if project.artwork:
                self.artwork_tab.set_artwork(project.artwork)
            else:
                self.artwork_tab.clear()

        self.output_tab.update_preview(project.book_info)
        self.book_info_tab.update_preview(self.output_tab.preview_label.text())
        
