import uuid
import time
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from shared.schemas.domain import ActionType, VenueSnapshot


class ActionRecommendation(BaseModel):
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the action",
    )
    created_at: float = Field(
        default_factory=time.time,
        description="Timestamp when the recommendation was created",
    )
    action_type: ActionType = Field(
        ...,
        description="Type of action to be taken",
    )
    priority: int = Field(
        ..., ge=1, le=5, description="Priority level of the action (1 = highest)"
    )
    target_zones: List[str] = Field(
        ..., description="List of zone IDs targeted by this action"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score of the recommendation"
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
    venue_summary: str = Field(
        default="",
        description=(
            "One-sentence AI-generated live status narration of the current venue "
            "state. Populated by the LLM reasoning cycle; empty string in degraded mode."
        ),
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


# ---------------------------------------------------------------------------
# Pre-Alert Engine schemas (Component 1 — predictive risk assessment)
# ---------------------------------------------------------------------------


class PreAlertRecommendation(BaseModel):
    """A single preemptive action recommendation for a zone approaching critical density."""

    zone_id: str = Field(..., min_length=1, description="Zone ID at risk")
    zone_name: str = Field(..., min_length=1, description="Human-readable zone name")
    risk_level: Literal["elevated", "high", "imminent"] = Field(
        ...,
        description="Assessed risk tier based on trajectory analysis",
    )
    estimated_minutes_to_critical: int = Field(
        ...,
        ge=0,
        description="Estimated minutes until the zone breaches the critical threshold (Rule C — computed by preprocessor)",
    )
    preemptive_action: str = Field(
        ...,
        description="LLM-recommended preemptive action to prevent breach",
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score of the recommendation"
    )
    rationale: str = Field(
        ..., description="Explanation of why this pre-alert was raised"
    )


class PreAlertOutput(BaseModel):
    """Structured output from the Predictive Pre-Alert Engine."""

    alerts: List[PreAlertRecommendation] = Field(
        default_factory=list,
        description="List of zones with active pre-alerts, sorted by risk severity",
    )
    degraded_mode: bool = Field(
        default=False,
        description="True if the LLM failed and a deterministic fallback was used",
    )


# ---------------------------------------------------------------------------
# Operator Chat schemas (Component 2 — natural language Q&A)
# ---------------------------------------------------------------------------


class OperatorQueryRequest(BaseModel):
    """Request body for POST /api/operator/query."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural-language question from the venue operator",
    )


class OperatorQueryResponse(BaseModel):
    """Structured response to an operator's natural-language question."""

    answer: str = Field(
        ...,
        min_length=1,
        description="Direct answer to the operator's question",
    )
    supporting_data: List[str] = Field(
        default_factory=list,
        description="Key data points from the venue state that support this answer",
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score of the response"
    )
    degraded_mode: bool = Field(
        default=False,
        description="True if the LLM failed and a fallback response was used",
    )


# ---------------------------------------------------------------------------
# GenAI Scenario Planner schemas (Component 3 — dynamic scenario generation)
# ---------------------------------------------------------------------------


class ScenarioIntent(BaseModel):
    """A single intent directive within a generated scenario specification.

    The LLM outputs creative *intent* (e.g., overwhelm zone X to 95 %).
    The preprocessor's deterministic intervention logic translates intents
    into actual count mutations — GenAI never does the arithmetic (Rule C).
    """

    target_zone: str = Field(..., description="Zone ID to apply the intent to")
    intent_type: Literal[
        "overwhelm", "evacuate", "incident_inject", "capacity_shift"
    ] = Field(..., description="Category of the scenario intent")
    intensity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Intensity parameter (0.0 = minimal effect, 1.0 = maximum effect)",
    )
    description: str = Field(
        ..., description="Human-readable description of what this intent does"
    )


class ScenarioSpec(BaseModel):
    """Structured specification for a generated scenario.

    Produced by the GenAI Scenario Planner, consumed by the deterministic
    intervention engine. The LLM provides creative diversity; the
    preprocessor enforces physics and arithmetic (Rule C).
    """

    name: str = Field(..., min_length=1, description="Scenario display name")
    narrative: str = Field(
        ...,
        min_length=1,
        description="1-2 sentence scenario narrative for the operator",
    )
    intents: List[ScenarioIntent] = Field(
        ..., min_length=1, description="List of scenario intents to apply"
    )
    estimated_duration_seconds: int = Field(
        default=12,
        ge=5,
        le=60,
        description="How long the scenario plays out in the simulation",
    )


class GenerateScenarioRequest(BaseModel):
    """Request body for POST /api/demo/generate-scenario."""

    description: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Natural-language description of the desired scenario",
    )
