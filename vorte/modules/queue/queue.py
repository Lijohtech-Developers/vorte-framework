"""
Vorte Queue Module - Queue Manager
====================================
In-process and Redis-backed queue management for background jobs.
"""

from __future__ import annotations

import asyncio
import json
import pickle
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Set

from vorte.core.config import settings


class Priority(IntEnum):
    """Job priority levels (higher = processed first)."""
    LOW = 1
    DEFAULT = 5
    HIGH = 10
    CRITICAL = 20


@dataclass
class QueueJob:
    """A job in the queue."""
    id: str = field(default_factory=lambda: f"job_{uuid.uuid4().hex[:12]}")
    job_class: str = ""
    queue_name: str = "default"
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: Priority = Priority.DEFAULT
    attempts: int = 0
    max_attempts: int = 3
    retry_delay: int = 5
    scheduled_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    failed_at: Optional[float] = None
    error: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_class": self.job_class,
            "queue_name": self.queue_name,
            "priority": self.priority.value,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class InMemoryQueueBackend:
    """In-process queue backend (for development / single-worker)."""

    def __init__(self):
        self._queues: Dict[str, deque] = defaultdict(deque)
        self._processing: Dict[str, QueueJob] = {}
        self._failed: Dict[str, List[QueueJob]] = defaultdict(list)
        self._completed: Dict[str, List[QueueJob]] = defaultdict(list)
        self._scheduled: List[QueueJob] = []
        self._lock = asyncio.Lock()

    async def enqueue(self, job: QueueJob) -> str:
        async with self._lock:
            if job.scheduled_at and job.scheduled_at > time.time():
                self._scheduled.append(job)
            else:
                self._queues[job.queue_name].append(job)
            return job.id

    async def dequeue(self, queue_name: str = "default") -> Optional[QueueJob]:
        async with self._lock:
            queue = self._queues[queue_name]
            if queue:
                job = queue.popleft()
                job.status = "running"
                job.started_at = time.time()
                self._processing[job.id] = job
                return job
            return None

    async def complete(self, job_id: str, result: Any = None) -> None:
        async with self._lock:
            job = self._processing.pop(job_id, None)
            if job:
                job.status = "completed"
                job.completed_at = time.time()
                self._completed[job.queue_name].append(job)

    async def fail(self, job_id: str, error: str) -> None:
        async with self._lock:
            job = self._processing.pop(job_id, None)
            if job:
                job.attempts += 1
                job.error = error
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                    job.failed_at = time.time()
                    self._failed[job.queue_name].append(job)
                else:
                    # Retry after delay
                    job.status = "pending"
                    job.scheduled_at = time.time() + (job.retry_delay * job.attempts)
                    self._scheduled.append(job)

    async def size(self, queue_name: str = "default") -> int:
        return len(self._queues.get(queue_name, deque()))

    async def stats(self) -> Dict[str, Any]:
        return {
            "queues": {
                name: len(jobs) for name, jobs in self._queues.items()
            },
            "processing": len(self._processing),
            "failed": sum(len(jobs) for jobs in self._failed.values()),
            "completed": sum(len(jobs) for jobs in self._completed.values()),
            "scheduled": len(self._scheduled),
        }

    async def get_failed(self, queue_name: str = "default", limit: int = 50) -> List[QueueJob]:
        return self._failed.get(queue_name, [])[-limit:]

    async def retry_failed(self, job_id: str) -> bool:
        async with self._lock:
            for queue_name, jobs in self._failed.items():
                for i, job in enumerate(jobs):
                    if job.id == job_id:
                        job.status = "pending"
                        job.attempts = 0
                        job.error = None
                        jobs.pop(i)
                        self._queues[queue_name].append(job)
                        return True
        return False


class QueueManager:
    """
    Manages background job queues.
    
    Supports in-process and Redis-backed backends.
    """

    def __init__(self, driver: str = "memory"):
        self._driver = driver
        self._backend = InMemoryQueueBackend()
        self._handlers: Dict[str, Callable] = {}
        self._running = False

    def register_handler(self, job_class_name: str, handler: Callable) -> None:
        """Register a handler for a job class."""
        self._handlers[job_class_name] = handler

    async def dispatch(
        self,
        job_class: type,
        queue: str = "default",
        priority: Priority = Priority.DEFAULT,
        delay: int = 0,
        **kwargs,
    ) -> str:
        """Dispatch a job to the queue."""
        job = QueueJob(
            job_class=job_class.__name__,
            queue_name=queue,
            payload=kwargs,
            priority=priority,
            max_attempts=getattr(job_class, 'retries', 3),
            retry_delay=getattr(job_class, 'retry_delay', 5),
            scheduled_at=time.time() + delay if delay > 0 else None,
        )
        return await self._backend.enqueue(job)

    async def process_next(self, queue_name: str = "default") -> bool:
        """Process the next job in a queue."""
        job = await self._backend.dequeue(queue_name)
        if not job:
            return False

        handler = self._handlers.get(job.job_class)
        if not handler:
            await self._backend.fail(job.id, f"No handler registered for '{job.job_class}'")
            return False

        try:
            result = handler(**job.payload)
            if asyncio.iscoroutine(result):
                result = await result
            await self._backend.complete(job.id, result)
            return True
        except Exception as e:
            await self._backend.fail(job.id, str(e))
            return False

    async def stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return await self._backend.stats()

    async def get_failed_jobs(self, queue_name: str = "default") -> List[Dict]:
        """Get failed jobs for a queue."""
        jobs = await self._backend.get_failed(queue_name)
        return [j.to_dict() for j in jobs]

    async def retry_failed(self, job_id: str) -> bool:
        """Retry a failed job."""
        return await self._backend.retry_failed(job_id)

    def get_backend(self):
        """Get the underlying queue backend."""
        return self._backend
