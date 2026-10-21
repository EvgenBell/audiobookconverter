"""Regression checks using unittest, Qt and the bundled FFmpeg. No test dependencies."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QImage, QCloseEvent, QPalette
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QDialogButtonBox, QProgressBar
from backend.chapters import ChapterManager, ChapterParser, parse_timestamp
from backend.ffmpeg import FFmpegBackend, set_ffmpeg_paths
from backend.metadata import MetadataHandler
from core.models import AudioFile, AppSettings, Artwork, BookInfo, Chapter, Job, JobStatus, OutputMode, OutputSettings
from core.project_io import Project
from core.queue_manager import QueueManager
from ui.chapters_dialog import ChaptersDialog
from ui.file_list import FileListWidget
from ui.main_window import MainWindow
from ui.settings_dialog import SettingsDialog
from ui.tabs.artwork_tab import ArtworkTab
from ui.tabs.output_tab import OutputTab
from ui.tabs.queue_tab import ConversionWorker, QueueTab
from ui.theme import apply_theme
from i18n.translator import tr, set_language
from utils.validators import validate_audio_file


APP = QApplication.instance() or QApplication([])
apply_theme(APP)


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(0.005)
    if not predicate():
        raise AssertionError("Timed out waiting for worker")


class LogicTests(unittest.TestCase):
    def test_parser_honors_parts_and_chapters_above_twenty(self):
        parser = ChapterParser("ru")
        self.assertEqual(parser.parse_filename("Часть 12.mp3").part_number, 12)
        self.assertEqual(parser.parse_filename("21 - Начало.mp3").chapter_number, 21)
        chapter = ChapterManager("ru").auto_generate_chapters([AudioFile("Часть 2_10-01.mp3", 5)])[0]
        self.assertEqual((chapter.part_number, chapter.chapter_number), (2, 10))
        self.assertEqual(chapter.title, "Часть 2 – Глава 10")

    def test_timestamps_reject_nan_and_invalid_fields(self):
        self.assertEqual(parse_timestamp("1:02:03.5"), 3723.5)
        for value in ("NaN", "inf", "-1", "1:60", "1:2:3:4", "1.5:20"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_timestamp(value)

    def test_filename_preserves_dots_in_book_title(self):
        self.assertEqual(OutputSettings(filename_template="{Title}").get_output_filename(BookInfo(title="Book 2.0")), "Book 2.0.m4b")

    def test_legacy_project_without_audio_stream_index_loads(self):
        project = Project.from_dict({"input_files": [{"path": "old.mp3", "duration": 1}]})
        self.assertIsNone(project.input_files[0].audio_stream_index)

    def test_queue_is_snapshot_and_starts_only_one_job(self):
        queue = QueueManager()
        info = BookInfo(title="Before")
        chapters = [Chapter("Before", 0, 1)]
        job = queue.create_job("Book", info, OutputSettings(), [AudioFile("a", 1)], chapters)
        info.title = chapters[0].title = "After"
        self.assertEqual(job.book_info.title, "Before")
        self.assertEqual(job.chapters[0].title, "Before")
        self.assertIs(queue.start_next(), job)
        self.assertIsNone(queue.start_next())

    def test_failed_save_preserves_original_file_and_project_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "book.abcproj"
            project = Project()
            project.save(str(path))
            original = path.read_bytes()
            project.book_info.title = "Changed"
            with patch("core.project_io.json.dump", side_effect=OSError("Disk full")):
                with self.assertRaises(OSError):
                    project.save(str(path))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_chapter_dialog_cancel_does_not_mutate_project(self):
        chapters = [Chapter("Original", 0, 2)]
        dialog = ChaptersDialog([AudioFile("test.wav", 2)], chapters)
        dialog.tree.setCurrentItem(dialog.tree.topLevelItem(0))
        dialog.name_edit.setText("Changed")
        dialog._rename_chapter()
        dialog.reject()
        self.assertEqual(chapters[0].title, "Original")

    def test_filename_preview_and_parts_mode(self):
        tab = OutputTab()
        tab.update_preview(BookInfo(title="Book"))
        tab.template_edit.setText("{Title}-{Part}.m4b")
        tab.set_settings(OutputSettings(filename_template="{Title}-{Part}.m4b", mode=OutputMode.SPLIT_BY_PARTS))
        self.assertEqual(tab.get_settings().mode, OutputMode.SPLIT_BY_PARTS)
        self.assertEqual(tab.preview_label.text(), "Book-1.m4b")

    def test_multiselect_reordering_keeps_all_files(self):
        widget = FileListWidget()
        files = [AudioFile(str(i), 1) for i in range(5)]
        widget.set_files(files)
        widget._move_rows([1, 2], 5)
        self.assertEqual([f.path for f in widget.get_files()], ["0", "3", "4", "1", "2"])
        widget._move_up()
        self.assertEqual([f.path for f in widget.get_files()], ["0", "3", "1", "2", "4"])

    def test_empty_queue_does_not_lock_interface(self):
        tab = QueueTab()
        states = []
        tab.conversion_state_changed.connect(lambda active, eta: states.append(active))
        tab._start_queue()
        self.assertNotIn(True, states)
        self.assertFalse(tab._workers)

    def test_cancel_save_blocks_new_project_and_close(self):
        with patch.object(MainWindow, "_load_settings", lambda self: AppSettings()), patch.object(MainWindow, "_check_ffmpeg", lambda self: None):
            window = MainWindow()
            window.tabs.book_info_tab.title_edit.setText("Keep this")
            self.assertTrue(window._modified)
            with patch.object(window, "_ask_save_changes", return_value=QMessageBox.Save), patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
                window._new_project()
                self.assertEqual(window.project.book_info.title, "Keep this")
                event = QCloseEvent()
                window.closeEvent(event)
                self.assertFalse(event.isAccepted())
            window._modified = False
            window.deleteLater()
            APP.processEvents()


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="abc-appearance-")
        self.addCleanup(self.temp.cleanup)
        config = Path(self.temp.name) / "config.json"
        config.write_text(json.dumps(AppSettings().to_dict()), encoding="utf-8")
        for target, replacement in (
            ("ui.main_window.get_config_path", lambda: config),
            ("ui.main_window.ensure_app_dir", lambda: None),
            ("ui.main_window.MainWindow._check_ffmpeg", lambda self: None),
        ):
            patcher = patch(target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.window = MainWindow()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window._modified = False
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        set_language("en")
        apply_theme(APP)

    def test_live_language_preserves_project_selection_and_queue(self):
        window = self.window
        window.tabs.book_info_tab.title_edit.setText("Title / Название")
        window.tabs.book_info_tab.genre_combo.setEditText("My genre")
        window.project.input_files = [AudioFile("video.mp4", 2, audio_stream_index=2)]
        window.project.chapters = [Chapter("My chapter", 0, 2)]
        window.file_list.set_files(window.project.input_files)
        window.file_list.table.selectRow(0)
        window.tabs.setCurrentIndex(2)
        queue = window.tabs.queue_tab
        queue.add_job_from_project(window.project)
        job = queue._queue.start_next()
        queue._on_worker_status(job.id, "status.writing_metadata")
        queue._queue.update_progress(job.id, 42, 12)
        snapshot = window.project.to_dict()
        window._modified = False
        for button, language in ((0, "ru"), (1, "en"), (0, "ru")):
            window.language_buttons.button(button).click()
            self.assertEqual(window.settings.language, language)
            self.assertEqual(window.tabs.tabText(0), tr("tabs.book_info"))
            self.assertEqual(window.file_list.add_btn.text(), tr("main.add_files"))
            self.assertEqual(window.menuBar().actions()[0].text(), tr("menu.file"))
            self.assertEqual(window.tabs.book_info_tab.title_edit.placeholderText(), tr("book_info.title"))
            self.assertEqual(window.tabs.output_tab.channels_combo.itemText(0), tr("output.auto"))
            self.assertEqual(queue.table.item(0, 1).text(), tr("status.writing_metadata"))
            self.assertEqual(queue.table.cellWidget(0, 2).findChild(QProgressBar).value(), 420)
            self.assertEqual(window.project.to_dict(), snapshot)
            self.assertEqual(window.tabs.book_info_tab.genre_combo.currentText(), "My genre")
            self.assertEqual(window.file_list.table.currentRow(), 0)
            self.assertEqual(window.tabs.currentIndex(), 2)
            self.assertFalse(window._modified)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.assertEqual(buttons.button(QDialogButtonBox.Cancel).text(), "Отмена")
        queue._queue.complete_job(job.id, "output.m4b")
        window.language_buttons.button(1).click()
        queue._clear_completed()
        self.assertEqual(queue.table.rowCount(), 0)

    def test_theme_and_language_are_saved_and_restored(self):
        self.window.language_buttons.button(0).click()
        self.window.theme_combo.setCurrentIndex(1)
        self.assertLess(APP.palette().color(QPalette.Window).lightness(), 80)
        restored = MainWindow()
        try:
            self.assertEqual((restored.settings.language, restored.settings.theme), ("ru", "dark"))
            self.assertEqual(restored.theme_combo.currentData(), "dark")
            restored.language_buttons.button(1).click()
            self.assertEqual(restored.settings.theme, "dark")
            restored.theme_combo.setCurrentIndex(0)
            self.assertGreater(APP.palette().color(QPalette.Window).lightness(), 220)
        finally:
            restored.deleteLater()
            APP.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertEqual(AppSettings.from_dict({}).theme, "light")
        invalid = AppSettings.from_dict({"theme": "unknown", "language": "unknown"})
        self.assertEqual((invalid.language, invalid.theme), ("en", "light"))

    def test_settings_dialog_applies_language_and_theme(self):
        def accept(dialog):
            dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("ru"))
            dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
            dialog._save_and_accept()
            return dialog.result()
        with patch.object(SettingsDialog, "exec", accept):
            self.window._show_settings()
        self.assertEqual(self.window.file_list.add_btn.text(), "Добавить файлы")
        self.assertEqual(self.window.theme_combo.currentData(), "dark")
        self.assertLess(APP.palette().color(QPalette.Window).lightness(), 80)


class FFmpegTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="abc-tests-")
        cls.root = Path(cls.temp.name)
        cls.backend = FFmpegBackend()
        if not cls.backend.check_available().available:
            cls.temp.cleanup()
            raise unittest.SkipTest("FFmpeg and FFprobe are required")
        set_ffmpeg_paths()
        cls.inputs = []
        for name, rate, channels, frequency in (
            ("Часть 1_01.wav", 44100, 1, 440),
            ("Часть 2_02.mp3", 48000, 2, 880),
            ("03.flac", 32000, 1, 660),
            ("04.m4a", 44100, 2, 330),
        ):
            path = cls.root / name
            cls.generate(path, 1.25, rate, channels, frequency)
            cls.inputs.append(cls.backend.probe_file(str(path)))
        cls.long_path = cls.root / "long.flac"
        cls.generate(cls.long_path, 301.25, 22050, 1, 440)
        cls.long_file = cls.backend.probe_file(str(cls.long_path))
        cls.video_path = cls.root / "Видео.MP4"
        subprocess.run([
            cls.backend.ffmpeg_path, "-v", "error",
            "-f", "lavfi", "-i", "color=size=16x16:rate=10:duration=3",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=2:sample_rate=44100",
            "-f", "lavfi", "-i", "sine=frequency=880:duration=1.25:sample_rate=48000",
            "-map", "0:v:0", "-map", "1:a:0", "-map", "2:a:0",
            "-c:v", "mpeg4", "-c:a", "aac", "-ac:a:1", "2",
            "-disposition:a:0", "0", "-disposition:a:1", "default", str(cls.video_path)
        ], check=True, capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    @classmethod
    def generate(cls, path, duration, rate, channels, frequency):
        subprocess.run([cls.backend.ffmpeg_path, "-v", "error", "-f", "lavfi", "-i",
                        f"sine=frequency={frequency}:duration={duration}", "-ar", str(rate),
                        "-ac", str(channels), str(path)], check=True, capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def make_job(self, folder, files=None, **settings):
        return Job("test", "Book", BookInfo(title="Книга", writer="Автор", narrator="Чтец", year=2024),
                   OutputSettings(output_folder=str(folder), filename_template="{Title}.m4b", **settings),
                   input_files=files or self.inputs)

    def convert(self, job):
        worker = ConversionWorker(job)
        worker.run()
        self.assertTrue(worker.result[0], worker.result[2])
        return Path(worker.result[1])

    def test_mp4_main_track_and_mixed_audiobook(self):
        import array
        for default_track, expected_index, duration, rate, channels, frequency in (
            (True, 2, 1.25, 48000, 2, 880),
            (False, 1, 2.0, 44100, 1, 220),
        ):
            with self.subTest(default_track=default_track), tempfile.TemporaryDirectory(dir=self.root) as folder:
                source = self.video_path
                if not default_track:
                    source = Path(folder) / "no-default.mp4"
                    subprocess.run([
                        self.backend.ffmpeg_path, "-v", "error", "-i", str(self.video_path),
                        "-map", "0", "-c", "copy", "-disposition:a", "0", str(source)
                    ], check=True, capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                audio = self.backend.probe_file(str(source))
                self.assertIsNotNone(audio)
                self.assertEqual(audio.audio_stream_index, expected_index)
                self.assertAlmostEqual(audio.duration, duration, delta=0.02)
                self.assertEqual((audio.sample_rate, audio.channels), (rate, channels))
                project = Project()
                project.input_files = [audio, self.inputs[0]]
                project_path = str(Path(folder) / "book.abcproj")
                project.save(project_path)
                restored = Project.load(project_path)
                self.assertEqual(restored.input_files, project.input_files)
                job = self.make_job(folder, restored.input_files)
                job.chapters = ChapterManager().auto_generate_chapters(job.input_files)
                output = self.convert(job)
                self.assertAlmostEqual(self.backend.probe_file(str(output)).duration, duration + 1.25, delta=0.08)
                chapters = self.backend.extract_m4b_info(str(output), False)[1]
                self.assertAlmostEqual(chapters[1]["start_time"], duration, delta=0.02)
                result = subprocess.run([
                    self.backend.ffprobe_path, "-v", "error", "-show_entries", "stream=codec_type",
                    "-of", "json", str(output)
                ], check=True, capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                self.assertNotIn("video", [s["codec_type"] for s in json.loads(result.stdout)["streams"]])
                for start, expected in ((0.25, frequency), (duration + 0.25, 440)):
                    result = subprocess.run([
                        self.backend.ffmpeg_path, "-v", "error", "-ss", str(start), "-i", str(output),
                        "-t", "0.5", "-ac", "1", "-ar", "8000", "-f", "f32le", "pipe:1"
                    ], check=True, capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    samples = array.array("f", result.stdout)
                    crossings = sum(a < 0 <= b for a, b in zip(samples, samples[1:]))
                    self.assertAlmostEqual(crossings * 2, expected, delta=5)

    def test_mp4_import_from_picker_and_folder(self):
        widget = FileListWidget()
        self.assertIn(str(self.video_path), widget._collect_audio_files_from_folder(str(self.root)))
        self.assertTrue(widget._is_supported_audio_path(str(self.video_path)))
        self.assertEqual(validate_audio_file(str(self.video_path)), (True, ""))
        with patch.object(QFileDialog, "getOpenFileNames", return_value=([str(self.video_path)], "")) as picker:
            widget._add_files()
            self.assertIn("*.mp4", picker.call_args.args[3])
        wait_for(lambda: not widget.is_loading)
        self.assertEqual(len(widget.get_files()), 1)
        self.assertEqual(widget.get_files()[0].audio_stream_index, 2)

    def test_mp4_without_audio_is_not_imported(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            source = Path(folder) / "silent.mp4"
            subprocess.run([
                self.backend.ffmpeg_path, "-v", "error", "-i", str(self.video_path),
                "-map", "0:v:0", "-c", "copy", str(source)
            ], check=True, capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            widget = FileListWidget()
            with patch.object(QMessageBox, "warning") as warning:
                widget._add_file_paths([str(source)])
                wait_for(lambda: not widget.is_loading)
                self.assertEqual(widget.get_files(), [])
                warning.assert_called_once()

    def test_mixed_formats_chapters_tags_cover_and_audio_order(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            job = self.make_job(folder)
            job.chapters = ChapterManager().auto_generate_chapters(job.input_files)
            job.chapters[0].title = "Глава = 1; # \\ конец\nСтрока 2"
            image_path = Path(folder) / "cover.png"
            image = QImage(1200, 600, QImage.Format_RGB32)
            image.fill(Qt.blue)
            image.save(str(image_path))
            tab = ArtworkTab()
            tab._load_image(str(image_path))
            tab.set_max_size(500)
            job.artwork = tab.get_artwork()
            output = self.convert(job)
            audio = self.backend.probe_file(str(output))
            self.assertAlmostEqual(audio.duration, 5.0, delta=0.08)
            self.assertEqual((audio.channels, audio.sample_rate), (2, 48000))
            _, chapters, _ = self.backend.extract_m4b_info(str(output), False)
            self.assertEqual([c["title"] for c in chapters], [c.title for c in job.chapters])
            self.assertEqual(MetadataHandler.read_metadata(str(output)).narrator, "Чтец")
            cover = MetadataHandler.extract_artwork(str(output))
            self.assertEqual(QImage.fromData(cover.embedded_data).size().width(), 500)
            # Decode short windows and count zero crossings to verify source order, not just duration.
            import array
            for index, expected in enumerate((440, 880, 660, 330)):
                result = subprocess.run([self.backend.ffmpeg_path, "-v", "error", "-ss", str(index * 1.25 + 0.25),
                                         "-i", str(output), "-t", "0.5", "-ac", "1", "-ar", "8000",
                                         "-f", "f32le", "pipe:1"], capture_output=True, check=True,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                samples = array.array("f", result.stdout)
                crossings = sum(a < 0 <= b for a, b in zip(samples, samples[1:]))
                self.assertAlmostEqual(crossings * 2, expected, delta=5)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            output = Path(folder) / "Книга.m4b"
            output.write_bytes(b"Keep existing data")
            result = self.convert(self.make_job(folder, self.inputs[:1]))
            self.assertNotEqual(result, output)
            self.assertEqual(output.read_bytes(), b"Keep existing data")

    def test_split_by_parts_and_merged_chapter_boundaries(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            job = self.make_job(folder, self.inputs[:2], mode=OutputMode.SPLIT_BY_PARTS)
            self.convert(job)
            outputs = sorted(Path(folder).glob("*.m4b"))
            self.assertEqual(len(outputs), 2)
            for output in outputs:
                self.assertAlmostEqual(self.backend.probe_file(str(output)).duration, 1.25, delta=0.08)
                chapters = self.backend.extract_m4b_info(str(output), False)[1]
                self.assertEqual(chapters[0]["start_time"], 0)

    def test_duration_split_inside_one_source_preserves_custom_chapters(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            job = self.make_job(folder, [self.long_file], mode=OutputMode.SPLIT_BY_DURATION, duration_target=5)
            job.chapters = [Chapter("Full chapter", 0, 301.25)]
            self.convert(job)
            outputs = sorted(Path(folder).glob("*.m4b"))
            self.assertEqual(len(outputs), 2)
            for output, expected in zip(outputs, (300, 1.25)):
                self.assertAlmostEqual(self.backend.probe_file(str(output)).duration, expected, delta=0.08)
                chapters = self.backend.extract_m4b_info(str(output), False)[1]
                self.assertEqual(chapters[0]["title"], "Full chapter")
                self.assertEqual(chapters[0]["start_time"], 0)
                self.assertAlmostEqual(chapters[-1]["end_time"], expected, delta=0.08)

    def test_failed_metadata_leaves_no_partial_book(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            worker = ConversionWorker(self.make_job(folder, self.inputs[:1]))
            with patch.object(MetadataHandler, "write_metadata", return_value=False):
                worker.run()
            self.assertFalse(worker.result[0])
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_pause_then_cancel_does_not_hang_or_publish_output(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            worker = ConversionWorker(self.make_job(folder, [self.long_file]))
            worker._backend.set_paused(True)
            worker.start()
            time.sleep(0.05)
            self.assertTrue(worker.isRunning())
            worker.cancel()
            self.assertTrue(worker.wait(5000))
            self.assertEqual(worker.result[2], "Cancelled")
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_queue_runs_two_jobs_and_cleans_up_threads(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            tab = QueueTab()
            project = Project()
            project.input_files = self.inputs[:1]
            project.output_settings = OutputSettings(output_folder=folder)
            tab.add_job_from_project(project)
            tab.add_job_from_project(project)
            tab._start_queue()
            wait_for(lambda: not tab._workers)
            self.assertEqual(tab._queue.stats.completed, 2)
            self.assertFalse(tab.stop_btn.isEnabled())

    def test_running_encoder_pause_resume_and_cancel(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            worker = ConversionWorker(self.make_job(folder, [self.long_file] * 4))
            worker.start()
            wait_for(lambda: worker._backend._process is not None)
            worker._backend.set_paused(True)
            time.sleep(0.15)
            self.assertTrue(worker.isRunning())
            worker._backend.set_paused(False)
            wait_for(lambda: worker._backend._decoder is not None)
            worker.cancel()
            self.assertTrue(worker.wait(5000))
            self.assertEqual(worker.result[2], "Cancelled")
            self.assertIsNone(worker._backend._process)
            self.assertIsNone(worker._backend._decoder)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_appearance_switch_during_conversion_keeps_worker_and_pause(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder, \
                patch.object(MainWindow, "_load_settings", lambda self: AppSettings()), \
                patch.object(MainWindow, "_save_settings", lambda self: None), \
                patch.object(MainWindow, "_check_ffmpeg", lambda self: None):
            window = MainWindow()
            queue = window.tabs.queue_tab
            queue.add_job_from_project(Project.from_dict({
                "input_files": [self.long_file.to_dict()],
                "output_settings": OutputSettings(output_folder=folder).to_dict(),
            }))
            queue._start_queue()
            queue._toggle_pause()
            worker = next(iter(queue._workers.values()))
            try:
                window.language_buttons.button(0).click()
                window.theme_combo.setCurrentIndex(1)
                APP.processEvents()
                self.assertIs(next(iter(queue._workers.values())), worker)
                self.assertTrue(queue._paused)
                self.assertTrue(window._is_converting)
                self.assertFalse(window.convert_btn.isEnabled())
                self.assertEqual(queue.pause_btn.text(), tr("queue.resume"))
                self.assertEqual(queue.table.item(0, 1).text(), tr("queue.paused"))
                queue._toggle_pause()
                wait_for(lambda: not queue._workers)
                self.assertEqual(queue._queue.stats.completed, 1)
            finally:
                if queue._workers:
                    queue._stop_queue()
                    wait_for(lambda: not queue._workers)
                window.deleteLater()
                APP.sendPostedEvents(None, QEvent.DeferredDelete)
                set_language("en")
                apply_theme(APP)

    def test_ogg_aac_and_wma_are_decoded(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            for extension in ("ogg", "aac", "wma"):
                with self.subTest(extension=extension):
                    source = Path(folder) / f"input.{extension}"
                    self.generate(source, 1.25, 44100, 1, 440)
                    audio = self.backend.probe_file(str(source))
                    self.assertIsNotNone(audio)
                    output = self.convert(self.make_job(folder, [audio]))
                    self.assertAlmostEqual(self.backend.probe_file(str(output)).duration, audio.duration, delta=0.1)

    def test_corrupt_source_reports_failure_and_cleans_staging(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            source = Path(folder) / "bad.mp3"
            source.write_bytes(b"invalid audio data")
            worker = ConversionWorker(self.make_job(folder, [AudioFile(str(source), 1)]))
            worker.run()
            self.assertFalse(worker.result[0])
            self.assertTrue(worker.result[2])
            self.assertEqual(list(Path(folder).iterdir()), [source])

    def test_import_is_asynchronous_and_deduplicated(self):
        widget = FileListWidget()
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(1)
        widget._add_file_paths([f.path for f in self.inputs] * 3)
        self.assertTrue(widget.is_loading)
        wait_for(lambda: not widget.is_loading)
        timer.stop()
        self.assertEqual(len(widget.get_files()), len(self.inputs))
        self.assertTrue(ticks)

    def test_imported_m4b_keeps_chapters_and_numeric_year(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            output = self.convert(self.make_job(folder, self.inputs[:2]))
            with patch.object(MainWindow, "_load_settings", lambda self: AppSettings()), patch.object(MainWindow, "_check_ffmpeg", lambda self: None):
                window = MainWindow()
                window._on_files_changed([self.backend.probe_file(str(output))])
                self.assertEqual(len(window.project.chapters), 2)
                self.assertEqual(window.project.book_info.year, 2024)
                window._modified = False
                window.deleteLater()
                APP.processEvents()


if __name__ == "__main__":
    unittest.main()
