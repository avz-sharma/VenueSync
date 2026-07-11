"""VenueSync — CSV Upload Security Endpoint.

Implements POST /api/upload with three layered defenses:
  1. 6 MB file-size hard cap (HTTP 413 if exceeded).
  2. Content-type sniffing via libmagic — never trusts the file extension (HTTP 415).
  3. 5,000-row parser cap to prevent memory exhaustion (HTTP 422).

Parsed CSV data is returned as a structured response.  Actual ingestion into
the reasoning pipeline must go through the DataSourceAdapter layer (Rule A).
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any

import magic
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_BYTES: int = 6 * 1024 * 1024  # 6 MB
MAX_CSV_ROWS: int = 5_000
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "text/plain",
        "text/csv",
        "application/csv",
    }
)

# ---------------------------------------------------------------------------
# Response Schema
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    """Structured response for a successful CSV upload."""

    status: str
    rows_parsed: int
    columns: list[str]
    preview: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=UploadResponse)
async def upload_csv(file: UploadFile) -> UploadResponse:
    """Accept a CSV file upload with strict security validation.

    Defenses:
      - Rejects files larger than 6 MB (HTTP 413).
      - Sniffs content-type from file header bytes instead of trusting the
        extension or client-supplied Content-Type (HTTP 415).
      - Caps the CSV parser at 5,000 rows to prevent memory exhaustion (HTTP 422).
    """
    # ------------------------------------------------------------------
    # 1. File-size enforcement — read entire body and check byte count
    # ------------------------------------------------------------------
    raw_bytes: bytes = await file.read()

    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File size ({len(raw_bytes):,} bytes) exceeds the "
                f"maximum allowed size of {MAX_FILE_SIZE_BYTES:,} bytes (6 MB)."
            ),
        )

    # ------------------------------------------------------------------
    # 2. Content-type sniffing — use libmagic on the raw bytes
    # ------------------------------------------------------------------
    detected_mime: str = magic.from_buffer(raw_bytes, mime=True)
    logger.info(f"Upload MIME detected: {detected_mime} (filename: {file.filename})")

    if detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type detected: '{detected_mime}'. "
                f"Expected a CSV file (text/plain or text/csv). "
                f"Content-type is determined by file content, not extension."
            ),
        )

    # ------------------------------------------------------------------
    # 3. CSV parsing with row cap
    # ------------------------------------------------------------------
    try:
        text_content: str = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"File could not be decoded as UTF-8: {exc}",
        )

    reader = csv.DictReader(io.StringIO(text_content))
    columns: list[str] = reader.fieldnames or []
    rows: list[dict[str, Any]] = []

    for row_number, row in enumerate(reader, start=1):
        if row_number > MAX_CSV_ROWS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"CSV exceeds the maximum allowed row count of "
                    f"{MAX_CSV_ROWS:,}. Processing stopped at row {row_number}."
                ),
            )
        rows.append(row)

    logger.info(
        f"CSV upload parsed successfully: {len(rows)} rows, {len(columns)} columns"
    )

    return UploadResponse(
        status="success",
        rows_parsed=len(rows),
        columns=columns,
        preview=rows[:5],
    )
