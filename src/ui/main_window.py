"""
Main window for AudioBookConverter.
"""
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QMenuBar, QMenu, QToolBar, QStatusBar,
    QMessageBox, QFileDialog, QApplication, QProgressBar, QLabel,
    QDialog, QPushButton, QDialogButtonBox, QScrollArea, QStyle, QComboBox, QButtonGroup
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QSignalBlocker, QTranslator, QLibraryInfo
from PySide6.QtGui import QAction, QIcon, QKeySequence, QCloseEvent

from core.models import AudioFile, BookInfo, OutputSettings, AppSettings, Chapter
from core.project_io import Project, APP_VERSION
from i18n.translator import tr, set_language, get_language
from ui.file_list import FileListWidget
from ui.tab_widget import MainTabWidget
from ui.chapters_dialog import ChaptersDialog
from ui.theme import apply_theme
from backend.ffmpeg import FFmpegBackend, get_backend
from backend.chapters import ChapterManager, format_duration
from backend.metadata import MetadataHandler
from utils.paths import get_app_dir, get_config_path, ensure_app_dir, get_default_output_folder
from utils.validators import validate_output_settings
import json


class MainWindow(QMainWindow):
    """Main application window."""

    conversion_started = Signal()
    conversion_finished = Signal()

    def __init__(self):
        super().__init__()

        self.project = Project()
        self.settings = self._load_settings()
        set_language(self.settings.language)
        apply_theme(QApplication.instance(), self.settings.theme)
        self._qt_translator = QTranslator(self)
        self.project.output_settings.output_folder = self.settings.default_output_folder
        self.project.output_settings.bitrate = self.settings.default_bitrate

        if self.settings.ffmpeg_path:
            from backend.ffmpeg import set_ffmpeg_paths
            set_ffmpeg_paths(self.settings.ffmpeg_path)

        self.ffmpeg_backend = get_backend()
        self.chapter_manager = ChapterManager(self.settings.language)
        self._modified = False
        self._edit_mode = False
        self._is_converting = False
        self._base_title = ""
        self._current_eta = 0.0
        self._close_after_stop = False

        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._setup_statusbar()

        self._apply_language()
        self.tabs.artwork_tab.set_max_size(self.settings.artwork_max_size)
        self.tabs.update_from_project(self.project)
        self.conversion_finished.connect(self._finish_close)

        self._title_timer = QTimer(self)
        self._title_timer.timeout.connect(self._update_title_eta)

        QTimer.singleShot(100, self._check_ffmpeg)
        
        # Set window icon - icon.ico is in project root (same level as src/)
        # main_window.py is in src/ui/, so project root is 3 levels up
        icon_path = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent.parent)) / "icon.ico"
        if not icon_path.exists():
            # Fallback to current working directory
            icon_path = Path.cwd() / "icon.ico"
        
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
    def _load_settings(self) -> AppSettings:
        """Load application settings from file."""
        config_path = get_config_path()

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return AppSettings.from_dict(data)
            except Exception:
                pass

        settings = AppSettings()
        settings.language = self._detect_language()
        settings.default_output_folder = get_default_output_folder()
        return settings

    def _save_settings(self) -> None:
        """Save application settings to file."""
        ensure_app_dir()
        config_path = get_config_path()

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.settings.to_dict(), f, indent=2)

    def _detect_language(self) -> str:
        """Detect system language."""
        import locale
        try:
            lang = locale.getdefaultlocale()[0]
            if lang and lang.lower().startswith("ru"):
                return "ru"
        except Exception:
            pass
        return "en"

    def _apply_language(self) -> None:
        """Apply the current language setting."""
        set_language(self.settings.language)
        self.chapter_manager = ChapterManager(self.settings.language)
        app = QApplication.instance()
        app.removeTranslator(self._qt_translator)
        if self.settings.language == "ru" and self._qt_translator.load(
            "qtbase_ru", QLibraryInfo.path(QLibraryInfo.TranslationsPath)
        ):
            app.installTranslator(self._qt_translator)
        for setter, key in self._menu_texts:
            setter(tr(key))
        self.subtitle.setText(tr("main.subtitle"))
        self.chapters_btn.setText(tr("chapters.title"))
        self.convert_btn.setText(tr("queue.add_to_queue"))
        self.language_buttons.button(0 if self.settings.language == "ru" else 1).setChecked(True)
        self.theme_combo.setAccessibleName(tr("settings.theme"))
        self.theme_combo.setToolTip(tr("settings.theme"))
        with QSignalBlocker(self.theme_combo):
            for index, theme in enumerate(("light", "dark")):
                self.theme_combo.setItemText(index, tr(f"settings.{theme}"))
            self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.settings.theme))
        self.file_list.retranslate_ui()
        self.tabs.retranslate_ui()
        status = "encoding" if self._is_converting else "reading" if self.file_list.is_loading else "ready"
        self.status_label.setText(tr(f"status.{status}"))
        self._update_duration_label()
        self._update_title()
        if self._is_converting:
            self._update_title_eta()

    def _set_language(self, language: str) -> None:
        if language != self.settings.language:
            self.settings.language = language
            self._apply_language()
            self._save_settings()

    def _set_theme(self) -> None:
        self.settings.theme = self.theme_combo.currentData()
        apply_theme(QApplication.instance(), self.settings.theme)
        self._save_settings()

    def _setup_ui(self) -> None:
        """Set up the main UI layout."""
        self._base_title = tr("app.title")
        self.setWindowTitle(self._base_title)
        self.setMinimumSize(1080, 760)
        self.resize(1280, 860)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(18)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("AudioBookConverter")
        title.setObjectName("heroTitle")
        self.subtitle = QLabel(tr("main.subtitle"))
        self.subtitle.setObjectName("subtitle")
        self.subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(self.subtitle)
        heading.addLayout(titles)
        heading.addStretch()
        badge = QLabel("AAC  /  M4B")
        badge.setObjectName("badge")
        heading.addWidget(badge, 0, Qt.AlignVCenter)
        self.language_buttons = QButtonGroup(self)
        for index, (label, language) in enumerate((("Rus", "ru"), ("Eng", "en"))):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setAccessibleName("Русский" if language == "ru" else "English")
            button.setToolTip(button.accessibleName())
            button.clicked.connect(lambda checked, lang=language: self._set_language(lang))
            self.language_buttons.addButton(button, index)
            heading.addWidget(button, 0, Qt.AlignVCenter)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(tr("settings.light"), "light")
        self.theme_combo.addItem(tr("settings.dark"), "dark")
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.settings.theme))
        self.theme_combo.currentIndexChanged.connect(self._set_theme)
        heading.addWidget(self.theme_combo, 0, Qt.AlignVCenter)
        layout.addLayout(heading)

        splitter = QSplitter(Qt.Horizontal)

        self.file_list = FileListWidget()
        self.file_list.files_changed.connect(self._on_files_changed)
        self.file_list.setMinimumWidth(460)
        self.file_list.loading_changed.connect(self._set_importing)
        splitter.addWidget(self.file_list)

        self.tabs = MainTabWidget(self.project, self)
        self.tabs.setMinimumWidth(510)
        self.tabs.set_main_window(self)
        self.tabs.project_changed.connect(self._mark_modified)
        splitter.addWidget(self.tabs)

        splitter.setSizes([510, 660])
        splitter.setChildrenCollapsible(False)

        layout.addWidget(splitter, 1)

    def _setup_menus(self) -> None:
        """Set up the menu bar."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu(tr("menu.file"))

        new_action = QAction(tr("menu.new_project"), self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)

        open_action = QAction(tr("menu.open_project"), self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)

        save_action = QAction(tr("menu.save_project"), self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)

        save_as_action = QAction(tr("menu.save_project_as"), self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self._save_project_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        settings_action = QAction(tr("menu.settings"), self)
        settings_action.triggered.connect(self._show_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction(tr("menu.exit"), self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menubar.addMenu(tr("menu.help"))

        about_action = QAction(tr("menu.about"), self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        self._menu_texts = [
            (file_menu.setTitle, "menu.file"), (help_menu.setTitle, "menu.help"),
            (new_action.setText, "menu.new_project"), (open_action.setText, "menu.open_project"),
            (save_action.setText, "menu.save_project"), (save_as_action.setText, "menu.save_project_as"),
            (settings_action.setText, "menu.settings"), (exit_action.setText, "menu.exit"),
            (about_action.setText, "menu.about"),
        ]

    def _setup_toolbar(self) -> None:
        """Set up the toolbar."""
        footer = QHBoxLayout()
        self.chapters_btn = QPushButton(tr("chapters.title"))
        self.chapters_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        self.chapters_btn.clicked.connect(self._show_chapters_dialog)
        self.chapters_btn.setEnabled(False)
        footer.addWidget(self.chapters_btn)
        footer.addStretch()
        self.convert_btn = QPushButton(tr("queue.add_to_queue"))
        self.convert_btn.setProperty("primary", True)
        self.convert_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowRight))
        self.convert_btn.clicked.connect(self._start_conversion)
        self.convert_btn.setMinimumWidth(220)
        self.convert_btn.setEnabled(False)
        footer.addWidget(self.convert_btn)
        self.centralWidget().layout().addLayout(footer)

    def _set_importing(self, importing: bool) -> None:
        self.menuBar().setEnabled(not importing)
        self.chapters_btn.setEnabled(not importing and bool(self.project.input_files))
        self.convert_btn.setEnabled(not importing and bool(self.project.input_files))
        self.status_label.setText(tr("status.reading" if importing else "status.ready"))
        if not importing and self._close_after_stop:
            self._finish_close()

    def _setup_statusbar(self) -> None:
        """Set up the status bar."""
        statusbar = self.statusBar()

        self.status_label = QLabel(tr("status.ready"))
        statusbar.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        statusbar.addPermanentWidget(self.progress_bar)

        self.duration_label = QLabel()
        statusbar.addPermanentWidget(self.duration_label)

    def _check_ffmpeg(self) -> None:
        """Check FFmpeg availability and show setup dialog if needed."""
        info = self.ffmpeg_backend.check_available()

        if not info.available:
            self._show_ffmpeg_setup_dialog()

    def _show_ffmpeg_setup_dialog(self) -> None:
        """Show dialog for FFmpeg setup."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("setup.welcome"))
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        msg = QLabel(f"<h3>{tr('setup.welcome')}</h3>")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        info = QLabel(tr("setup.ffmpeg_required") + "\n\n" + tr("setup.ffmpeg_instructions"))
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox()

        settings_btn = QPushButton(tr("setup.open_settings"))
        settings_btn.clicked.connect(lambda: (dialog.accept(), self._show_settings()))
        buttons.addButton(settings_btn, QDialogButtonBox.AcceptRole)

        layout.addWidget(buttons)

        dialog.exec()

    def _new_project(self) -> None:
        """Create a new project."""
        if self._modified:
            reply = self._ask_save_changes()
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Save and not self._save_project():
                return

        self.project.clear()
        self.project.output_settings.output_folder = self.settings.default_output_folder
        self.project.output_settings.bitrate = self.settings.default_bitrate
        self._edit_mode = False
        self._modified = False
        self.file_list.clear()
        self.tabs.update_from_project(self.project)
        self._update_duration_label()
        self._update_title()

    def _open_project(self) -> None:
        """Open an existing project file."""
        if self._modified:
            reply = self._ask_save_changes()
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Save and not self._save_project():
                return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialogs.open_project"),
            "",
            f"{tr('dialogs.project_files')} (*.abcproj)"
        )

        if file_path:
            self._load_project_file(file_path)

    def _load_project_file(self, file_path: str) -> None:
        """Load a project from a file."""
        try:
            self.project = Project.load(file_path)

            valid, missing = self.project.validate_files()

            if missing:
                self._handle_missing_files(missing)

            self.file_list.set_files(self.project.input_files)
            self.tabs.update_from_project(self.project)
            self._modified = False
            self._update_duration_label()
            self._update_title()

        except Exception as e:
            QMessageBox.critical(
                self,
                tr("errors.project_load_error"),
                tr("errors.project_load_error").format(error=str(e))
            )

    def _handle_missing_files(self, missing: list[str]) -> None:
        """Handle missing files when loading a project."""
        from PySide6.QtWidgets import QDialog, QListWidget, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("errors.missing_files"))
        dialog.setMinimumSize(500, 300)

        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel(tr("errors.missing_files_message")))

        list_widget = QListWidget()
        list_widget.addItems(missing)
        layout.addWidget(list_widget)

        layout.addWidget(QLabel(tr("errors.relink_prompt")))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        browse_btn = QPushButton(tr("output.browse"))
        browse_btn.clicked.connect(lambda: self._relink_files(dialog))
        buttons.addButton(browse_btn, QDialogButtonBox.ActionRole)

        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()

    def _relink_files(self, parent: QWidget) -> None:
        """Browse for a folder to relink missing files."""
        folder = QFileDialog.getExistingDirectory(
            parent,
            tr("dialogs.select_folder")
        )

        if folder:
            relinked = self.project.relink_files(folder)
            if relinked > 0:
                QMessageBox.information(
                    self,
                    "Relinked",
                    tr("main.relinked", count=relinked)
                )

    def _save_project(self) -> bool:
        """Save the current project."""
        if self.project.file_path:
            return self._save_project_file(self.project.file_path)
        else:
            return self._save_project_as()

    def _save_project_as(self) -> bool:
        """Save the project with a new name."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialogs.save_project"),
            "",
            f"{tr('dialogs.project_files')} (*.abcproj)"
        )

        if file_path:
            if not file_path.endswith(".abcproj"):
                file_path += ".abcproj"
            return self._save_project_file(file_path)
        return False

    def _save_project_file(self, file_path: str) -> bool:
        """Save the project to a file."""
        try:
            self._update_project_from_ui()

            self.project.save(file_path)
            self._modified = False
            self._update_title()
            return True

        except Exception as e:
            QMessageBox.critical(
                self,
                tr("errors.project_save_error"),
                tr("errors.project_save_error").format(error=str(e))
            )
            return False

    def _update_project_from_ui(self) -> None:
        """Update the project from the current UI state."""
        self.project.input_files = self.file_list.get_files()
        self.project.book_info = self.tabs.book_info_tab.get_book_info()
        self.project.output_settings = self.tabs.output_tab.get_settings()
        self.project.artwork = self.tabs.artwork_tab.get_artwork()

    def _ask_save_changes(self) -> QMessageBox.StandardButton:
        """Ask the user whether to save changes."""
        reply = QMessageBox.question(
            self,
            tr("dialogs.save_changes"),
            tr("dialogs.save_changes_message"),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
        )
        return reply

    def _show_settings(self) -> None:
        """Show the settings dialog."""
        from ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.settings = dialog.get_settings()
            self._apply_language()
            apply_theme(QApplication.instance(), self.settings.theme)
            self._save_settings()

            from backend.ffmpeg import set_ffmpeg_paths
            set_ffmpeg_paths(self.settings.ffmpeg_path)
            self.ffmpeg_backend = get_backend()
            self.tabs.artwork_tab.set_max_size(self.settings.artwork_max_size)

    def _show_about(self) -> None:
        """Show the about dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("about.title"))
        dialog.setMinimumSize(450, 320)

        layout = QVBoxLayout(dialog)

        title_label = QLabel(f"<h2>{tr('app.title')}</h2>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        desc_label = QLabel(tr("about.description"))
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        version_label = QLabel(f"<p><b>{tr('about.version')}:</b> {APP_VERSION}</p>")
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)

        layout.addSpacing(15)

        dev_info = QLabel(
            f"<b>{tr('about.developer')}:</b> Евгений Белявский<br><br>"
            "<b>Telegram:</b> <a href='https://t.me/evgen_rus'>@evgen_rus</a>"
        )
        dev_info.setAlignment(Qt.AlignCenter)
        dev_info.setOpenExternalLinks(True)
        layout.addWidget(dev_info)

        layout.addSpacing(10)

        disclaimer = QLabel(
            f"<i>{tr('about.disclaimer')}</i>"
        )
        disclaimer.setAlignment(Qt.AlignCenter)
        disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)

        layout.addStretch()

        close_btn = QPushButton(tr("dialogs.close"))
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

    def _show_chapters_dialog(self) -> None:
        """Show the chapters editor dialog."""
        if not self.project.input_files:
            QMessageBox.information(
                self,
                tr("chapters.title"),
                tr("errors.no_files")
            )
            return

        dialog = ChaptersDialog(
            self.project.input_files,
            self.project.chapters,
            self.settings.language,
            self
        )

        if dialog.exec():
            self.project.chapters = dialog.get_chapters()
            self._mark_modified()

    def _on_files_changed(self, files: list[AudioFile]) -> None:
        """Handle changes to the file list."""
        self.project.input_files = files.copy()
        self._update_duration_label()
        self._mark_modified()

        if self.settings.auto_parse_chapters:
            self.project.chapters = self.chapter_manager.auto_generate_chapters(files)
        else:
            self.project.chapters = []

        if len(files) == 1 and files[0].extension == ".m4b":
            self._enter_edit_mode(files[0])
        else:
            self._edit_mode = False

    def _enter_edit_mode(self, m4b_file: AudioFile) -> None:
        """Enter edit mode for an existing M4B file."""
        self._edit_mode = True

        metadata, chapters, _ = self.ffmpeg_backend.extract_m4b_info(m4b_file.path, extract_artwork=False)

        book_info = MetadataHandler.read_metadata(m4b_file.path)
        if book_info:
            self.project.book_info = book_info
            self.tabs.book_info_tab.set_book_info(book_info)
            self.tabs.output_tab.update_preview(book_info)
            self.tabs.book_info_tab.update_preview(self.tabs.output_tab.preview_label.text())

        if chapters:
            self.project.chapters = [
                Chapter(
                    title=ch.get("title", ""),
                    start_time=ch.get("start_time", 0),
                    end_time=ch.get("end_time", 0),
                    source_file_index=0
                )
                for ch in chapters
            ]

        artwork = MetadataHandler.extract_artwork(m4b_file.path)
        if artwork:
            self.project.artwork = artwork
            self.tabs.artwork_tab.set_artwork(artwork)

    def _update_duration_label(self) -> None:
        """Update the duration label in the status bar."""
        can_edit = bool(self.project.input_files) and not self._is_converting and not self.file_list.is_loading
        self.chapters_btn.setEnabled(can_edit)
        self.convert_btn.setEnabled(can_edit)
        total = self.project.get_total_duration()
        count = len(self.project.input_files)

        if count > 0:
            duration_str = format_duration(total)
            self.duration_label.setText(
                f"{tr('main.total_duration')}: {duration_str} | {tr('main.files_count', count=count)}"
            )
        else:
            self.duration_label.setText("")

    def _update_title(self) -> None:
        """Update the window title."""
        title = tr("app.title")

        if self.project.file_path:
            name = Path(self.project.file_path).stem
            title = f"{name} - {title}"

        if self._modified:
            title = f"* {title}"

        self._base_title = title
        if not self._is_converting:
            self.setWindowTitle(title)

    def _update_title_eta(self) -> None:
        """Update window title with ETA during conversion."""
        if self._current_eta > 0:
            eta_str = format_duration(self._current_eta)
            self.setWindowTitle(f"{tr('queue.time_remaining', time=eta_str)} - {self._base_title}")
        else:
            self.setWindowTitle(self._base_title)

    def _mark_modified(self) -> None:
        """Mark the project as modified."""
        self._modified = True
        self._update_title()

    def _start_conversion(self) -> None:
        """Start the conversion process."""
        if not self.project.input_files:
            QMessageBox.warning(self, tr("app.title"), tr("errors.no_files"))
            return

        self._update_project_from_ui()

        valid, errors = validate_output_settings(self.project.output_settings)
        if not valid:
            QMessageBox.warning(self, tr("app.title"), "\n".join(errors))
            return

        self.tabs.queue_tab.add_job_from_project(self.project)
        self.tabs.setCurrentIndex(3)

    def set_converting_state(self, is_converting: bool, eta: float = 0.0) -> None:
        """Set the converting state and enable/disable UI elements."""
        self._current_eta = eta
        if self._is_converting == is_converting:
            return
        self._is_converting = is_converting

        self.file_list.setEnabled(not is_converting)
        self.tabs.book_info_tab.setEnabled(not is_converting)
        self.tabs.artwork_tab.setEnabled(not is_converting)
        self.tabs.output_tab.setEnabled(not is_converting)
        
        for i in range(3):
            self.tabs.setTabEnabled(i, not is_converting)
        
        self.menuBar().setEnabled(not is_converting)
        
        self.chapters_btn.setEnabled(not is_converting and bool(self.project.input_files))
        self.convert_btn.setEnabled(not is_converting and bool(self.project.input_files))
        self.status_label.setText(tr("status.encoding" if is_converting else "status.ready"))

        if is_converting:
            self.tabs.setCurrentIndex(3)
            self._title_timer.start(1000)
            self.conversion_started.emit()
        else:
            self._title_timer.stop()
            self._update_title()
            self.conversion_finished.emit()

    def _finish_close(self) -> None:
        if self._close_after_stop:
            self._close_after_stop = False
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event."""
        if self.file_list.is_loading:
            self._close_after_stop = True
            self.file_list._probe_worker.requestInterruption()
            event.ignore()
            return
        if self._is_converting:
            reply = QMessageBox.question(
                self,
                tr("app.title"),
                tr("main.stop_and_exit"),
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            self._close_after_stop = True
            self.tabs.queue_tab._stop_queue()
            event.ignore()
            return

        if self._modified:
            reply = self._ask_save_changes()

            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.Save and not self._save_project():
                event.ignore()
                return

        self._save_settings()
        event.accept()
        
