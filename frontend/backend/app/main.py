from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.auth import router as auth_router
from app.core.config import settings
from app.core.database import engine
from app.core.telemetry import configure_telemetry
from app.models.entities import Base
from app.api.v1.router import router as v1_router


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