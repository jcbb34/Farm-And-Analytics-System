"""Expected transient database conflicts have a clear, retryable API response."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.db_concurrency import DatabaseLockBusy


async def database_lock_busy_handler(request: Request, error: DatabaseLockBusy):
    logging.getLogger("joross.database").info(
        "database_busy path=%s resource=%s code=%s",
        request.url.path,
        error.resource,
        error.result_code,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Farm data is being updated. Try again shortly.",
            "code": "DATABASE_BUSY",
        },
        headers={"Retry-After": "2", "Cache-Control": "no-store"},
    )


async def stale_record_handler(request: Request, error):
    from app.services.record_editing import CONFLICT_MESSAGE
    return JSONResponse(
        status_code=409,
        content={"detail": CONFLICT_MESSAGE, "code": "RECORD_CONFLICT"},
        headers={"Cache-Control": "no-store"},
    )
