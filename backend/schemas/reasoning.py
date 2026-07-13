import uuid
from typing import List

from pydantic import BaseModel, Field

from shared.schemas.domain import VenueSnapshot


class ActionRecommendation(BaseModel):
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the action",
    )
    action_type: str = Field(
        ...,
        description="Type of action to be taken (e.g. redirect_crowd, dispatch_security)",
    )
    priority: int = Field(
        ..., description="Priority level of the action (e.g. 1 for highest)"
    )
    target_zones: List[str] = Field(
        ..., description="List of zone IDs targeted by this action"
    )
    confidence: float = Field(
        ..., description="Confidence score of the recommendation between 0 and 1"
    )
    rationale: str = Field(
        ..., description="Explanation of why this action is recommended"
    )
    predicted_impact: str = Field(
        ..., description="Predicted impact of taking this action"
    )


class ReasoningCycleOutput(BaseModel):
    actions: List[ActionRecommendation] = Field(
        ..., description="List of recommended actions"
    )
    degraded_mode: bool = Field(
        default=False,
        description="Flag indicating if the system is running in fallback/degraded mode",
    )


class DebriefRequest(BaseModel):
    """Request body for POST /api/analytics/debrief.

    Accepts an ordered list of VenueSnapshot objects that represent a complete
    event run sequence.  The list must contain at least one snapshot (enforced
    by the route handler, not here, to return a meaningful HTTP 422).
    """

    snapshots: List[VenueSnapshot] = Field(
        ...,
        description="Ordered sequence of VenueSnapshot objects from a completed event run.",
    )
