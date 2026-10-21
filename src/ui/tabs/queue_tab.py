"""
Queue tab for AudioBookConverter.
Handles job management and conversion progress.
"""
import os
import time
import tempfile
import math
from dataclasses import replace
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QMessageBox, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QThread, Slot

from core.models import Job, JobStatus, OutputMode
from core.queue_manager import QueueManager, QueueEvent
from backend.ffmpeg import FFmpegBackend, get_backend
from backend.chapters import format_duration, ChapterManager
from backend.metadata import MetadataHandler
from core.project_io import Project
from i18n.translator import tr
from utils.paths import get_unique_filename
from utils.validators import validate_output_settings, validate_filename


class ConversionWorker(QThread):
    """Worker thread for conversion jobs."""

    progress = Signal(str, float, float)  # job_id, progress, eta
    status = Signal(str, str)

    def __init__(self, job: Job, parent=None):
        super().__init__(parent)
        self.job = job
        self._is_cancelled = False
        backend = get_backend()
        self._backend = FFmpegBackend(backend.ffmpeg_path, backend.ffprobe_path)
        self.result = (False, "", "Conversion did not finish")

    def run(self) -> None:
        try:
            self.result = self._convert()
        except Exception as exc:
            self.result = (False, "", str(exc))
        if self._is_cancelled:
            self.result = (False, "", "Cancelled")

    def _convert(self) -> tuple[bool, str, str]:
        job = self.job
        valid, errors = validate_output_settings(job.output_settings)
        if not valid:
            return False, "", "\n".join(errors)
        if not job.input_files or any(
            not math.isfinite(f.duration) or f.duration <= 0 or not os.path.isfile(f.path)
            for f in job.input_files
        ):
            return False, "", "Missing input file or invalid duration"
        total = sum(f.duration for f in job.input_files)
        if not job.chapters:
            job.chapters = ChapterManager().auto_generate_chapters(job.input_files)
        issues = ChapterManager().validate_chapters(job.chapters, total)
        if issues:
            return False, "", "\n".join(issues)

        boundaries = [0.0]
        mode = job.output_settings.mode
        if mode == OutputMode.SPLIT_BY_DURATION:
            limit = job.output_settings.duration_target * 60
            boundaries.extend(i * limit for i in range(1, math.ceil(total / limit)))
        elif mode == OutputMode.SPLIT_BY_PARTS:
            for previous, chapter in zip(job.chapters, job.chapters[1:]):
                if previous.part_number != chapter.part_number:
                    boundaries.append(chapter.start_time)
        boundaries.append(total)
        count = len(boundaries) - 1
        last_output = ""
        started = time.monotonic()
        # Only completed, tagged files are published. Failed and cancelled parts are removed.
        with tempfile.TemporaryDirectory(prefix=".abc-", dir=job.output_settings.output_folder) as temp:
            for index, (begin, end) in enumerate(zip(boundaries, boundaries[1:]), 1):
                if not self._backend.wait_until_resumed():
                    return False, "", "Cancelled"
                filename = job.output_settings.get_output_filename(job.book_info, index if count > 1 else 0)
                if count > 1 and "{Part}" not in job.output_settings.filename_template:
                    stem, ext = os.path.splitext(filename)
                    filename = f"{stem} Part {index}{ext}"
                valid, error = validate_filename(filename)
                if not valid:
                    return False, "", error
                chapters = [replace(ch, start_time=max(ch.start_time, begin) - begin,
                                    end_time=min(ch.end_time, end) - begin)
                            for ch in job.chapters if ch.start_time < end and ch.end_time > begin]
                staging = os.path.join(temp, "encoding.m4b")
                self.status.emit(job.id, "status.encoding")

                def on_progress(percent: float, eta: float) -> None:
                    overall = (begin + percent / 100 * (end - begin)) / total * 99
                    elapsed = time.monotonic() - started
                    remaining = elapsed * (100 - overall) / overall if overall > 0 else 0
                    self.progress.emit(job.id, overall, remaining)

                success, error = self._backend.concat_and_encode(
                    job.input_files, staging, job.output_settings, on_progress,
                    chapters, start_time=begin, duration=end - begin)
                if not success:
                    return False, "", error
                encoded = self._backend.probe_file(staging)
                if not encoded or abs(encoded.duration - (end - begin)) > max(0.25, (end - begin) * 0.0001):
                    return False, "", "Encoded duration does not match the source interval"
                if not self._backend.wait_until_resumed():
                    return False, "", "Cancelled"
                book_info = job.book_info
                if count > 1:
                    book_info = replace(book_info, title=f"{book_info.title or job.name} (Part {index})")
                self.status.emit(job.id, "status.writing_metadata")
                if not MetadataHandler.write_metadata(staging, book_info):
                    return False, "", "Failed to write metadata"
                if job.artwork and job.artwork.has_artwork:
                    if not MetadataHandler.write_artwork(staging, job.artwork):
                        return False, "", "Failed to write artwork"
                if not self._backend.wait_until_resumed():
                    return False, "", "Cancelled"
                filename = get_unique_filename(job.output_settings.output_folder, filename)
                last_output = os.path.join(job.output_settings.output_folder, filename)
                os.rename(staging, last_output)
        return True, job.output_settings.output_folder if count > 1 else last_output, ""

    def cancel(self) -> None:
        self._is_cancelled = True
        self._backend.cancel()


class QueueTab(QWidget):
    """Tab for managing the conversion queue."""

    # Signal emitted when conversion state changes (is_converting, eta)
    conversion_state_changed = Signal(bool, float)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._queue = QueueManager()
        self._workers: dict[str, ConversionWorker] = {}
        self._start_time: float = 0
        self._main_window = None
        self._paused = False
        self._stopping = False

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)

        # Queue table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            tr("queue.job_name"),
            tr("queue.status"),
            tr("queue.progress"),
            tr("queue.elapsed"),
            tr("queue.eta"),
            tr("queue.details")
        ])

        # Configure table
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)

        layout.addWidget(self.table)

        # Button row
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton(tr("queue.start"))
        self.start_btn.setProperty("primary", True)
        self.start_btn.setEnabled(False)
        self.pause_btn = QPushButton(tr("queue.pause_all"))
        self.stop_btn = QPushButton(tr("queue.stop_all"))
        self.clear_btn = QPushButton(tr("queue.clear_completed"))

        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.pause_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.clear_btn)

        layout.addLayout(btn_layout)

    def retranslate_ui(self) -> None:
        self.table.setHorizontalHeaderLabels([
            tr(f"queue.{key}") for key in ("job_name", "status", "progress", "elapsed", "eta", "details")
        ])
        self.start_btn.setText(tr("queue.start"))
        self.pause_btn.setText(tr("queue.resume" if self._paused else "queue.pause_all"))
        self.stop_btn.setText(tr("queue.stop_all"))
        self.clear_btn.setText(tr("queue.clear_completed"))
        for job in self._queue.jobs:
            row = self._find_row_by_job_id(job.id)
            if row < 0:
                continue
            item = self.table.item(row, 1)
            key = f"queue.{job.status.value}"
            if job.status == JobStatus.RUNNING:
                key = item.data(Qt.UserRole) or key
            item.setText(tr(key))
            if not job.error_message and job.output_settings.sample_rate.value == "auto":
                self.table.item(row, 5).setText(f"{job.output_settings.bitrate} kbps | {tr('output.auto')}")

    def _connect_signals(self) -> None:
        """Connect signals."""
        self.start_btn.clicked.connect(self._start_queue)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.stop_btn.clicked.connect(self._stop_queue)
        self.clear_btn.clicked.connect(self._clear_completed)

        # Queue callbacks
        self._queue.add_callback(QueueEvent.JOB_ADDED, self._on_job_added)
        self._queue.add_callback(QueueEvent.JOB_STARTED, self._on_job_started)
        self._queue.add_callback(QueueEvent.JOB_PROGRESS, self._on_job_progress)
        self._queue.add_callback(QueueEvent.JOB_COMPLETED, self._on_job_completed)
        self._queue.add_callback(QueueEvent.JOB_FAILED, self._on_job_failed)
        self._queue.add_callback(QueueEvent.JOB_CANCELLED, self._on_job_cancelled)

    def add_job_from_project(self, project: Project) -> None:
        """Add a new job from a project."""
        job_name = project.book_info.title or "Untitled"

        job = self._queue.create_job(
            name=job_name,
            book_info=project.book_info,
            output_settings=project.output_settings,
            input_files=project.input_files,
            chapters=project.chapters,
            artwork=project.artwork
        )

        self._add_job_to_table(job)
        self._refresh_controls()

    def _add_job_to_table(self, job: Job) -> None:
        """Add a job to the table."""
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Job name
        name_item = QTableWidgetItem(job.name)
        name_item.setData(Qt.UserRole, job.id)
        self.table.setItem(row, 0, name_item)

        # Status
        status_item = QTableWidgetItem(tr("queue.pending"))
        self.table.setItem(row, 1, status_item)

        # Progress (use progress bar widget)
        progress_widget = QWidget()
        progress_layout = QHBoxLayout(progress_widget)
        progress_layout.setContentsMargins(4, 4, 4, 4)

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 1000)              # 0.0%..100.0%
        progress_bar.setValue(0)
        progress_bar.setFormat("%.1f%%" % 0.0)
        progress_bar.setTextVisible(True)
        progress_layout.addWidget(progress_bar)

        self.table.setCellWidget(row, 2, progress_widget)

        # Elapsed
        elapsed_item = QTableWidgetItem("-")
        self.table.setItem(row, 3, elapsed_item)

        # ETA
        eta_item = QTableWidgetItem("-")
        self.table.setItem(row, 4, eta_item)

        # Details: bitrate and sample rate
        bitrate = job.output_settings.bitrate
        sample_rate = job.output_settings.sample_rate.value
        if sample_rate == "auto":
            sample_rate_str = tr("output.auto")
        else:
            sample_rate_str = f"{int(sample_rate) // 1000} kHz"
        details_text = f"{bitrate} kbps | {sample_rate_str}"
        details_item = QTableWidgetItem(details_text)
        self.table.setItem(row, 5, details_item)

    def _start_queue(self) -> None:
        if self._workers or not self._queue.stats.pending:
            return
        self._queue.reset()
        self._stopping = False
        self._paused = False
        self._process_next_job()

    def _process_next_job(self) -> None:
        if not self._workers and not self._stopping:
            job = self._queue.start_next()
            if job:
                worker = ConversionWorker(job, self)
                worker.progress.connect(self._on_worker_progress)
                worker.finished.connect(self._on_worker_finished)
                worker.status.connect(self._on_worker_status)
                self._workers[job.id] = worker
                worker.start()
        self._refresh_controls()

    def _refresh_controls(self) -> None:
        active = bool(self._workers)
        self.start_btn.setEnabled(not active and self._queue.stats.pending > 0)
        self.pause_btn.setEnabled(active and not self._stopping)
        self.pause_btn.setText(tr("queue.resume") if self._paused else tr("queue.pause_all"))
        self.stop_btn.setEnabled(active and not self._stopping)
        self.clear_btn.setEnabled(not active)
        self.conversion_state_changed.emit(active, 0)
        if self._main_window:
            self._main_window.set_converting_state(active, 0)

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        for worker in self._workers.values():
            worker._backend.set_paused(self._paused)
        if self._paused:
            self._queue.pause_all()
        else:
            self._queue.resume_all()
            self._process_next_job()
        for worker in self._workers.values():
            row = self._find_row_by_job_id(worker.job.id)
            self.table.item(row, 1).setText(tr("queue.paused" if self._paused else "queue.running"))
        self._refresh_controls()

    def set_main_window(self, main_window) -> None:
        self._main_window = main_window

    def _stop_queue(self) -> None:
        self._stopping = True
        self._paused = False
        for worker in self._workers.values():
            worker.cancel()
        self._queue.stop_all()
        self._refresh_controls()

    def _clear_completed(self) -> None:
        """Clear completed jobs from the table."""
        completed = {job.id for job in self._queue.jobs
                     if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)}
        self._queue.clear_completed()
        for row in reversed(range(self.table.rowCount())):
            if self.table.item(row, 0).data(Qt.UserRole) in completed:
                self.table.removeRow(row)

    def _find_row_by_job_id(self, job_id: str) -> int:
        """Find the table row for a job ID."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == job_id:
                return row
        return -1

    def _on_job_added(self, job: Job) -> None:
        """Handle job added event."""
        pass

    def _on_job_started(self, job: Job) -> None:
        """Handle job started event."""
        row = self._find_row_by_job_id(job.id)
        if row >= 0:
            self.table.item(row, 1).setText(tr("queue.running"))

    def _on_job_progress(self, job: Job) -> None:
        """Handle job progress event."""
        row = self._find_row_by_job_id(job.id)
        if row >= 0:
            # Update progress bar
            progress_widget = self.table.cellWidget(row, 2)
            if progress_widget:
                progress_bar = progress_widget.findChild(QProgressBar)
                if progress_bar:
                    value = int(round(job.progress * 10))       # 0..1000
                    progress_bar.setValue(value)
                    progress_bar.setFormat(f"{job.progress:.1f}%")

            # Update elapsed
            if job.elapsed_time > 0:
                self.table.item(row, 3).setText(format_duration(job.elapsed_time))

            # Update ETA
            if job.eta > 0:
                self.table.item(row, 4).setText(format_duration(job.eta))

    def _on_job_completed(self, job: Job) -> None:
        """Handle job completed event."""
        row = self._find_row_by_job_id(job.id)
        if row >= 0:
            self.table.item(row, 1).setText(tr("queue.completed"))

            # Update progress to 100%
            progress_widget = self.table.cellWidget(row, 2)
            if progress_widget:
                progress_bar = progress_widget.findChild(QProgressBar)
                if progress_bar:
                    progress_bar.setValue(1000)
                    progress_bar.setFormat("100.0%")

    def _on_job_failed(self, job: Job) -> None:
        """Handle job failed event."""
        row = self._find_row_by_job_id(job.id)
        if row >= 0:
            self.table.item(row, 1).setText(tr("queue.failed"))
            if job.error_message:
                self.table.item(row, 5).setText(job.error_message.splitlines()[0])
                self.table.item(row, 5).setToolTip(job.error_message)

    def _on_job_cancelled(self, job: Job) -> None:
        """Handle job cancelled event."""
        row = self._find_row_by_job_id(job.id)
        if row >= 0:
            self.table.item(row, 1).setText(tr("queue.cancelled"))

    @Slot(str, float, float)
    def _on_worker_progress(self, job_id: str, progress: float, eta: float) -> None:
        """Handle worker progress signal."""
        if self._stopping or self._paused:
            return
        self._queue.update_progress(job_id, progress, eta)
        # Update main window with current ETA
        if self._main_window and eta > 0:
            self._main_window.set_converting_state(True, eta)

    @Slot()
    def _on_worker_finished(self) -> None:
        # QThread.finished means run() has returned: it is now safe to release the worker.
        worker = self.sender()
        job_id = worker.job.id
        success, output_path, error = worker.result
        self._workers.pop(job_id, None)
        worker.deleteLater()
        if error == "Cancelled" or self._stopping:
            self._queue.cancel_job(job_id)
        elif success:
            self._queue.complete_job(job_id, output_path)
        else:
            self._queue.fail_job(job_id, error)
        self._process_next_job()

    @Slot(str, str)
    def _on_worker_status(self, job_id: str, status: str) -> None:
        """Handle worker status signal."""
        if self._stopping or self._paused:
            return
        row = self._find_row_by_job_id(job_id)
        if row >= 0:
            self.table.item(row, 1).setData(Qt.UserRole, status)
            self.table.item(row, 1).setText(tr(status))
