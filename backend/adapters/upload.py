"""VenueSync — Custom Upload Data Adapter (Stub).

Placeholder for a future adapter that parses user-uploaded CSV files
into the Canonical Data Schema.  All methods currently raise
``NotImplementedError`` — swap ``DATA_SOURCE=upload`` to activate once
implemented.
"""

from __future__ import annotations

from backend.adapters.base import DataSourceAdapter
from shared.schemas.domain import Staff, VenueSnapshot, Zone


class CustomUploadAdapter(DataSourceAdapter):
    """Parses uploaded CSV data into the canonical schema.

    Future implementation contract:
    - Accept CSV file paths or in-memory buffers via constructor.
    - Normalize column names to canonical field names.
    - Validate all rows against Pydantic schemas (reject on failure).
    - Generate timezone-aware timestamps from CSV date/time columns.

    Currently stubbed — all methods raise ``NotImplementedError``.
    """

    async def get_snapshot(self) -> VenueSnapshot:
        """Parse a CSV snapshot into a VenueSnapshot.

        Raises
        ------
        NotImplementedError
            This adapter is not yet implemented.
        """
        raise NotImplementedError(
            "CustomUploadAdapter.get_snapshot() is not yet implemented. "
            "Set DATA_SOURCE=synthetic to use the synthetic data generator."
        )

    async def get_venue_graph(self) -> list[Zone]:
        """Parse venue zone definitions from an uploaded CSV.

        Raises
        ------
        NotImplementedError
            This adapter is not yet implemented.
        """
        raise NotImplementedError(
            "CustomUploadAdapter.get_venue_graph() is not yet implemented. "
            "Set DATA_SOURCE=synthetic to use the synthetic data generator."
        )

    async def get_staff_roster(self) -> list[Staff]:
        """Parse staff roster data from an uploaded CSV.

        Raises
        ------
        NotImplementedError
            This adapter is not yet implemented.
        """
        raise NotImplementedError(
            "CustomUploadAdapter.get_staff_roster() is not yet implemented. "
            "Set DATA_SOURCE=synthetic to use the synthetic data generator."
        )
