"""Tests for the CSV Upload Security Endpoint (POST /api/upload).

Validates the three layered defenses:
  1. 6 MB file-size hard cap → HTTP 413
  2. Content-type sniffing via libmagic → HTTP 415
  3. 5,000-row parser cap → HTTP 422
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_csv_bytes(rows: int, cols: int = 3) -> bytes:
    """Generate a valid CSV file as bytes with the given number of data rows."""
    header = ",".join(f"col_{i}" for i in range(cols))
    lines = [header]
    for row_num in range(rows):
        lines.append(",".join(f"val_{row_num}_{c}" for c in range(cols)))
    return "\n".join(lines).encode("utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejects_oversized_file() -> None:
    """Uploading a file larger than 6 MB must return HTTP 413."""
    # Generate content just over 6 MB
    oversized_content = b"a" * (6 * 1024 * 1024 + 1)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/upload",
            files={"file": ("big_file.csv", io.BytesIO(oversized_content), "text/csv")},
        )

    assert response.status_code == 413
    assert "6" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rejects_non_csv_content() -> None:
    """Uploading a PNG file disguised as .csv must return HTTP 415.

    Content-type is determined by libmagic sniffing, not the file extension.
    """
    # PNG magic bytes (minimal valid PNG header)
    png_header = (
        b"\x89PNG\r\n\x1a\n"  # PNG signature
        b"\x00\x00\x00\rIHDR"  # IHDR chunk
        b"\x00\x00\x00\x01"  # Width: 1
        b"\x00\x00\x00\x01"  # Height: 1
        b"\x08\x02"  # Bit depth 8, color type 2 (RGB)
        b"\x00\x00\x00"  # Compression, filter, interlace
        b"\x90wS\xde"  # CRC
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/upload",
            files={"file": ("sneaky.csv", io.BytesIO(png_header), "text/csv")},
        )

    assert response.status_code == 415
    assert (
        "image/png" in response.json()["detail"].lower()
        or "Unsupported" in response.json()["detail"]
    )


@pytest.mark.asyncio
async def test_rejects_csv_exceeding_row_limit() -> None:
    """Uploading a CSV with more than 5,000 rows must return HTTP 422."""
    csv_bytes = _build_csv_bytes(rows=5001)

    # Patch magic.from_buffer to return text/csv (since the content is valid CSV text)
    with patch("backend.api.upload.magic.from_buffer", return_value="text/csv"):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/upload",
                files={"file": ("large.csv", io.BytesIO(csv_bytes), "text/csv")},
            )

    assert response.status_code == 422
    assert "5,000" in response.json()["detail"]


@pytest.mark.asyncio
async def test_accepts_valid_csv() -> None:
    """A valid CSV within all limits must return HTTP 200 with parsed data."""
    csv_bytes = _build_csv_bytes(rows=10, cols=3)

    # Patch magic.from_buffer to return text/csv
    with patch("backend.api.upload.magic.from_buffer", return_value="text/csv"):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/upload",
                files={"file": ("valid.csv", io.BytesIO(csv_bytes), "text/csv")},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["rows_parsed"] == 10
    assert len(data["columns"]) == 3
    assert len(data["preview"]) == 5  # Preview capped at first 5 rows


@pytest.mark.asyncio
async def test_accepts_csv_at_exact_row_limit() -> None:
    """A CSV with exactly 5,000 rows must be accepted (boundary condition)."""
    csv_bytes = _build_csv_bytes(rows=5000, cols=2)

    with patch("backend.api.upload.magic.from_buffer", return_value="text/csv"):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/upload",
                files={"file": ("boundary.csv", io.BytesIO(csv_bytes), "text/csv")},
            )

    assert response.status_code == 200
    assert response.json()["rows_parsed"] == 5000
