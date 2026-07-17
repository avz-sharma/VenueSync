"""VenueSync — FastAPI Application Entry Point.

Provides core system endpoints (/health, /version) and serves as the
mounting point for all feature routers.
"""

# Load environment variables from .env before anything else reads os.getenv()
from dotenv import load_dotenv

load_dotenv()

import logging
import uuid
import structlog
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def sanitize_personal_data(logger, method_name, event_dict):
    """Sanitize raw uploaded personal data."""
    sensitive_keys = {
        "personal_data",
        "ssn",
        "phone",
        "email",
        "raw_incident_notes",
        "untrusted_incident_note",
        "pii",
    }
    for key in list(event_dict.keys()):
        if key.lower() in sensitive_keys or any(
            s in key.lower() for s in ["personal", "ssn", "email"]
        ):
            event_dict[key] = "***SANITIZED***"
    return event_dict


structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.contextvars.merge_contextvars,
        sanitize_personal_data,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Response schemas (Pydantic v2, strict)
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Schema for the /health endpoint response."""

    status: str


class VersionResponse(BaseModel):
    """Schema for the /version endpoint response."""

    version: str


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

APP_VERSION: str = "0.1.0"

app: FastAPI = FastAPI(
    title="VenueSync",
    description="AI command center for crowd management and operational intelligence.",
    version=APP_VERSION,
)

if os.getenv("ENVIRONMENT") == "development":
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_url, "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def structlog_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    reasoning_cycle_id = str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        reasoning_cycle_id=reasoning_cycle_id,
        path=request.url.path,
        method=request.method,
    )

    logger.info("Request started")
    response = await call_next(request)
    logger.info("Request completed", status_code=response.status_code)

    return response


# Include the API router
from backend.api.routes import router as api_router

app.include_router(api_router, prefix="/api")

# Include the upload security router
from backend.api.upload import router as upload_router

app.include_router(upload_router, prefix="/api")

# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return a simple health status for liveness probes."""
    return HealthResponse(status="healthy")


@app.get("/version", response_model=VersionResponse)
async def get_version() -> VersionResponse:
    """Return the current semantic version of the application."""
    return VersionResponse(version=APP_VERSION)


# ---------------------------------------------------------------------------
# Static Assets and SPA Fallback
# ---------------------------------------------------------------------------

# Mount static assets if they exist (to avoid crashing locally if dist is not built yet)
assets_path = Path("frontend/dist/assets")
if assets_path.is_dir():
    app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")

    candidate = Path("frontend/dist") / full_path
    if candidate.is_file():
        return FileResponse(candidate)

    index_path = Path("frontend/dist/index.html")
    if index_path.is_file():
        return FileResponse(index_path)

    # If the frontend is not built at all, just return 404
    raise HTTPException(status_code=404, detail="Frontend not built")
