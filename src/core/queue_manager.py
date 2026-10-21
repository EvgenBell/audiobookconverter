"""
Queue manager for AudioBookConverter.
Handles job scheduling, progress tracking, and worker management.
"""
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional
from enum import Enum
from datetime import datetime
import time
from copy import deepcopy

from .models import Job, JobStatus, BookInfo, OutputSettings, AudioFile, Chapter, Artwork


class QueueEvent(Enum):
    JOB_ADDED = "job_added"
    JOB_STARTED = "job_started"
    JOB_PROGRESS = "job_progress"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    JOB_CANCELLED = "job_cancelled"
    JOB_PAUSED = "job_paused"
    QUEUE_CLEARED = "queue_cleared"


@dataclass
class QueueStats:
    """Statistics about the job queue."""
    total_jobs: int = 0
    pending: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0


class QueueManager:
    """Manages the conversion job queue."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._job_order: list[str] = []
        self._current_job: Optional[str] = None
        self._is_paused: bool = False
        self._is_stopped: bool = False
        self._callbacks: dict[QueueEvent, list[Callable]] = {
            event: [] for event in QueueEvent
        }
        self._start_time: Optional[float] = None

    @property
    def jobs(self) -> list[Job]:
        """Get all jobs in order."""
        return [self._jobs[jid] for jid in self._job_order if jid in self._jobs]

    @property
    def current_job(self) -> Optional[Job]:
        """Get the currently running job."""
        if self._current_job and self._current_job in self._jobs:
            return self._jobs[self._current_job]
        return None

    @property
    def is_processing(self) -> bool:
        """Check if the queue is actively processing jobs."""
        return self._current_job is not None and not self._is_paused

    @property
    def stats(self) -> QueueStats:
        """Get queue statistics."""
        stats = QueueStats(total_jobs=len(self._jobs))

        for job in self._jobs.values():
            if job.status == JobStatus.PENDING:
                stats.pending += 1
            elif job.status == JobStatus.RUNNING:
                stats.running += 1
            elif job.status == JobStatus.COMPLETED:
                stats.completed += 1
            elif job.status == JobStatus.FAILED:
                stats.failed += 1
            elif job.status == JobStatus.CANCELLED:
                stats.cancelled += 1

        return stats

    def add_callback(self, event: QueueEvent, callback: Callable) -> None:
        """Register a callback for a queue event."""
        self._callbacks[event].append(callback)

    def remove_callback(self, event: QueueEvent, callback: Callable) -> None:
        """Remove a registered callback."""
        if callback in self._callbacks[event]:
            self._callbacks[event].remove(callback)

    def _emit(self, event: QueueEvent, job: Optional[Job] = None) -> None:
        """Emit an event to all registered callbacks."""
        for callback in self._callbacks[event]:
            try:
                callback(job)
            except Exception as e:
                print(f"Callback error for {event}: {e}")

    def create_job(
        self,
        name: str,
        book_info: BookInfo,
        output_settings: OutputSettings,
        input_files: list[AudioFile],
        chapters: list[Chapter] = None,
        artwork: Optional[Artwork] = None
    ) -> Job:
        """Create a new job and add it to the queue."""
        job_id = str(uuid.uuid4())[:8]

        job = Job(
            id=job_id,
            name=name,
            book_info=deepcopy(book_info),
            output_settings=deepcopy(output_settings),
            input_files=deepcopy(input_files),
            chapters=deepcopy(chapters) if chapters else [],
            artwork=deepcopy(artwork),
            status=JobStatus.PENDING
        )

        self._jobs[job_id] = job
        self._job_order.append(job_id)
        self._emit(QueueEvent.JOB_ADDED, job)

        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def remove_job(self, job_id: str) -> bool:
        """Remove a job from the queue."""
        if job_id in self._jobs:
            job = self._jobs[job_id]

            # Don't remove running jobs
            if job.status == JobStatus.RUNNING:
                return False

            del self._jobs[job_id]
            self._job_order.remove(job_id)
            return True

        return False

    def update_progress(self, job_id: str, progress: float, eta: float = 0) -> None:
        """Update the progress of a running job."""
        if job_id in self._jobs:
            job = self._jobs[job_id]
            job.progress = min(100.0, max(0.0, progress))

            if self._start_time:
                job.elapsed_time = time.time() - self._start_time

            job.eta = eta
            self._emit(QueueEvent.JOB_PROGRESS, job)

    def start_next(self) -> Optional[Job]:
        """Start the next pending job in the queue."""
        if self._is_paused or self._is_stopped or self._current_job:
            return None

        # Find next pending job
        for job_id in self._job_order:
            job = self._jobs.get(job_id)
            if job and job.status == JobStatus.PENDING:
                self._current_job = job_id
                job.status = JobStatus.RUNNING
                job.progress = 0.0
                self._start_time = time.time()
                self._emit(QueueEvent.JOB_STARTED, job)
                return job

        return None

    def complete_job(self, job_id: str, output_path: str = "") -> None:
        """Mark a job as completed."""
        if job_id in self._jobs:
            job = self._jobs[job_id]
            job.status = JobStatus.COMPLETED
            job.progress = 100.0
            job.output_path = output_path

            if self._current_job == job_id:
                self._current_job = None
                self._start_time = None

            self._emit(QueueEvent.JOB_COMPLETED, job)

    def fail_job(self, job_id: str, error: str = "") -> None:
        """Mark a job as failed."""
        if job_id in self._jobs:
            job = self._jobs[job_id]
            job.status = JobStatus.FAILED
            job.error_message = error

            if self._current_job == job_id:
                self._current_job = None
                self._start_time = None

            self._emit(QueueEvent.JOB_FAILED, job)

    def cancel_job(self, job_id: str) -> None:
        """Cancel a job."""
        if job_id in self._jobs:
            job = self._jobs[job_id]
            job.status = JobStatus.CANCELLED

            if self._current_job == job_id:
                self._current_job = None
                self._start_time = None

            self._emit(QueueEvent.JOB_CANCELLED, job)

    def pause_all(self) -> None:
        """Pause all running jobs."""
        self._is_paused = True

        if self._current_job and self._current_job in self._jobs:
            job = self._jobs[self._current_job]
            job.status = JobStatus.PAUSED
            self._emit(QueueEvent.JOB_PAUSED, job)

    def resume_all(self) -> None:
        """Resume paused jobs."""
        self._is_paused = False

        if self._current_job and self._current_job in self._jobs:
            job = self._jobs[self._current_job]
            if job.status == JobStatus.PAUSED:
                job.status = JobStatus.RUNNING
                self._emit(QueueEvent.JOB_STARTED, job)

    def stop_all(self) -> None:
        """Stop all jobs."""
        self._is_stopped = True
        self._is_paused = False

        # Cancel current job
        if self._current_job:
            self.cancel_job(self._current_job)

        # Reset all pending jobs
        for job in self._jobs.values():
            if job.status == JobStatus.PENDING:
                self.cancel_job(job.id)

        self._current_job = None
        self._start_time = None

    def reset(self) -> None:
        """Reset the queue state for new operations."""
        self._is_stopped = False
        self._is_paused = False

    def clear_completed(self) -> None:
        """Remove all completed, failed, or cancelled jobs."""
        to_remove = [
            jid for jid, job in self._jobs.items()
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
        ]

        for jid in to_remove:
            del self._jobs[jid]
            self._job_order.remove(jid)

        if to_remove:
            self._emit(QueueEvent.QUEUE_CLEARED)

    def clear_all(self) -> None:
        """Clear the entire queue."""
        self._jobs.clear()
        self._job_order.clear()
        self._current_job = None
        self._start_time = None
        self._is_stopped = False
        self._is_paused = False
        self._emit(QueueEvent.QUEUE_CLEARED)
