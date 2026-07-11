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
from fastapi import FastAPI, Request
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
