"""
Vorte Queue Module - Main Module
==================================
Background job processing with support for retries, scheduling, and priorities.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from vorte.core.module import Module, ModuleMeta, ModulePriority
from vorte.core.response import success_response, error_response
from vorte.modules.queue.queue import QueueManager, Priority
from vorte.modules.queue.worker import Worker
from vorte.modules.queue.scheduler import Scheduler
from vorte.modules.auth.guards import IsAdmin


class QueueModule(Module):
    """
    Background job processing module.
    
    Usage:
        app.register(QueueModule(driver='redis'))
    """

    meta = ModuleMeta(
        name="queue",
        version="1.0.0",
        description="Background job processing with retries, scheduling, and priorities",
        priority=ModulePriority.QUEUE,
    )

    def __init__(self, *, driver: str = "redis", default_retries: int = 3, default_retry_delay: int = 5):
        super().__init__(driver=driver, default_retries=default_retries, default_retry_delay=default_retry_delay)
        self._driver = driver
        self._manager: Optional[QueueManager] = None
        self._worker: Optional[Worker] = None
        self._scheduler: Optional[Scheduler] = None
        self._router = APIRouter(prefix="/queue", tags=["Queue"])

    def register(self, app) -> None:
        self._manager = QueueManager(driver=self._driver)
        self._worker = Worker(queues=["default"])
        self._scheduler = Scheduler(self._manager)

        if hasattr(app, 'container'):
            app.container.register_instance(QueueManager, self._manager)
            app.container.register_instance(Worker, self._worker)
            app.container.register_instance(Scheduler, self._scheduler)

        self._setup_routes()
        app.include_router(self._router)

    def _setup_routes(self):
        @self._router.get("/stats")
        async def queue_stats():
            stats = await self._manager.stats()
            return success_response(stats)

        @self._router.get("/failed")
        async def failed_jobs():
            jobs = await self._manager.get_failed_jobs()
            return success_response(jobs)

        @self._router.post("/retry/{job_id}")
        async def retry_job(job_id: str):
            ok = await self._manager.retry_failed(job_id)
            if not ok:
                return error_response("JOB_NOT_FOUND", f"Failed job '{job_id}' not found", status_code=404)
            return success_response({"message": f"Job '{job_id}' queued for retry"})

    @property
    def manager(self) -> QueueManager:
        return self._manager
