import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware

from app.core.auth import router as auth_router
from app.core.config import settings
from app.core.database import engine
from app.core.event_bus import get_event_bus
from app.core.telemetry import configure_telemetry
from app.models.entities import Base
from app.api.v1.router import router as v1_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Fleet Studio API",
    version="0.1.0",
    description="Desired-state governance and assurance control plane for Hermes fleets.",
    lifespan=lifespan,
)
allowed_origins = [settings.frontend_origin]
if not settings.auth_required:
    allowed_origins.append("http://127.0.0.1:3000")
    if "http://localhost:3000" not in allowed_origins:
        allowed_origins.append("http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax", https_only=settings.auth_required)
app.include_router(v1_router)
app.include_router(auth_router)
configure_telemetry(app)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fleet-studio-api"}


@app.get("/stream/{workflow_id}")
async def stream_workflow_events(workflow_id: str):
    """Server-Sent Events (SSE) streaming endpoint for live execution terminal."""
    bus = get_event_bus()

    async def event_generator():
        async for event in bus.subscribe(workflow_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/approve/{workflow_id}")
async def approve_workflow(workflow_id: str, request: Request):
    """Approve or reject a paused task."""
    bus = get_event_bus()
    payload = await request.json() if (await request.body()) else {}
    approved = payload.get("approved", True)
    bus.publish(workflow_id, {
        "type": "approval_resolved" if approved else "approval_rejected",
        "approved": approved,
        "message": "Operator approval recorded.",
    })
    return {"status": "ok", "workflow_id": workflow_id, "approved": approved}


@app.post("/cancel/{workflow_id}")
async def cancel_workflow(workflow_id: str):
    """Cancel an active execution."""
    bus = get_event_bus()
    bus.publish(workflow_id, {
        "type": "workflow_failed",
        "status": "failed",
        "error": "Execution cancelled by operator.",
    })
    return {"status": "cancelled", "workflow_id": workflow_id}


@app.get("/status/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Retrieve status of an active or completed workflow."""
    bus = get_event_bus()
    history = bus.get_history(workflow_id)
    terminal = next((e for e in reversed(history) if e.get("type") in ("workflow_completed", "workflow_failed")), None)
    if terminal:
        return {"workflow_id": workflow_id, "status": "COMPLETED" if terminal.get("type") == "workflow_completed" else "FAILED"}
    return {"workflow_id": workflow_id, "status": "RUNNING" if history else "PENDING"}
