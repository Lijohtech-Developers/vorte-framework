"""Global error handler middleware."""

import traceback
from fastapi import Request
from fastapi.responses import JSONResponse

from vorte.core.response import _generate_request_id


class ErrorHandlerMiddleware:
    """Catches unhandled exceptions and returns standard error responses."""

    async def __call__(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            request_id = getattr(request.state, "request_id", _generate_request_id())
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred",
                    },
                    "meta": {"request_id": request_id},
                },
            )
