"""VenueSync — Backend Schema Exports.

Re-exports canonical data models from ``shared.schemas.domain`` so that
backend code can import from either location::

    from backend.schemas import VenueSnapshot   # ← works
    from shared.schemas import VenueSnapshot    # ← also works
"""

from shared.schemas.domain import (
    Incident,
    Occupancy,
    Staff,
    VenueSnapshot,
    Zone,
)

from .reasoning import ActionRecommendation, ReasoningCycleOutput

__all__: list[str] = [
    "Incident",
    "Occupancy",
    "Staff",
    "VenueSnapshot",
    "Zone",
    "ActionRecommendation",
    "ReasoningCycleOutput",
]
