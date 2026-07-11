"""Tests for core system endpoints: /health and /version."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.asyncio
async def test_health_endpoint_returns_healthy() -> None:
    """GET /health must return 200 with {"status": "healthy"}."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data: dict[str, str] = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_version_endpoint_returns_semver() -> None:
    """GET /version must return 200 with a semantic version string."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/version")

    assert response.status_code == 200
    data: dict[str, str] = response.json()
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health_response_schema() -> None:
    """Response body must validate against the HealthResponse Pydantic model."""
    from backend.main import HealthResponse

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    # This will raise ValidationError if the schema doesn't match
    model = HealthResponse.model_validate(response.json())
    assert model.status == "healthy"


@pytest.mark.asyncio
async def test_version_response_schema() -> None:
    """Response body must validate against the VersionResponse Pydantic model."""
    from backend.main import VersionResponse

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/version")

    model = VersionResponse.model_validate(response.json())
    assert model.version == "0.1.0"
