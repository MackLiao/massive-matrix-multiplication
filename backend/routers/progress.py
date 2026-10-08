import asyncio
import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from ..models.schemas import JobCompleteEvent, TileStatusEvent
from ..models.state import jobs

router = APIRouter(prefix="/api")


@router.get("/jobs/{job_id}/progress")
async def job_progress(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(job.event_queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keepalive
                yield {"event": "keepalive", "data": ""}
                continue

            if event is None:
                # Job finished
                yield {"event": "done", "data": "{}"}
                break

            if isinstance(event, TileStatusEvent):
                yield {
                    "event": "tile",
                    "data": json.dumps(event.model_dump()),
                }
            elif isinstance(event, JobCompleteEvent):
                yield {
                    "event": "complete",
                    "data": json.dumps(event.model_dump()),
                }

    return EventSourceResponse(event_generator())
