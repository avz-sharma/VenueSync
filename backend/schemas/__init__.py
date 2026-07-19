"""VenueSync — Backend Schema Exports.

Re-exports canonical data models from ``shared.schemas.domain`` so that
backend code can import from either location::

    from backend.schemas import VenueSnapshot   # ← works
    from shared.schemas import VenueSnapshot    # ← also works
"""

from shared.schemas.domain import (
    ActionType,
    HistoricalMetrics,
    Incident,
    IntensityPoint,
    Occupancy,
    Staff,
    VenueSnapshot,
    Zone,
)

from .reasoning import (
    ActionRecommendation,
    DebriefRequest,
    GenerateScenarioRequest,
    OperatorQueryRequest,
    OperatorQueryResponse,
    PreAlertOutput,
    PreAlertRecommendation,
    ReasoningCycleOutput,
    ScenarioIntent,
    ScenarioSpec,
)

__all__: list[str] = [
    "ActionType",
    "HistoricalMetrics",
    "Incident",
    "IntensityPoint",
    "Occupancy",
    "Staff",
    "VenueSnapshot",
    "Zone",
    "ActionRecommendation",
    "DebriefRequest",
    "GenerateScenarioRequest",
    "OperatorQueryRequest",
    "OperatorQueryResponse",
    "PreAlertOutput",
    "PreAlertRecommendation",
    "ReasoningCycleOutput",
    "ScenarioIntent",
    "ScenarioSpec",
]
