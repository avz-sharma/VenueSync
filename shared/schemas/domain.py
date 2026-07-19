"""VenueSync — Canonical Data Schema.

Defines the immutable Pydantic v2 data contract for all venue state.
Every data source adapter must emit instances of these models.

Design principles:
  - Models are pure data structures (frozen=True).
  - @model_validator methods enforce data *sanity* guardrails only.
  - All mathematical derivations (pct_capacity, rate of change, etc.)
    are computed by backend/preprocessor/ per Rule C.
  - All datetime fields must be timezone-aware.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Action taxonomy — single source of truth for valid action types
# ---------------------------------------------------------------------------

ActionType = Literal[
    "redirect_crowd",
    "dispatch_medical",
    "dispatch_security",
    "open_emergency_exit",
    "broadcast_announcement",
]


# ---------------------------------------------------------------------------
# Entity models
# ---------------------------------------------------------------------------


class IntensityPoint(BaseModel):
    """A single spatial data point for heat-density mapping.

    Represents a coordinate within a zone's 2-D layout with an associated
    intensity value.  The preprocessor populates these points (Rule C);
    they are consumed by the frontend canvas for heatmap rendering.
    """

    model_config = ConfigDict(frozen=True)

    x: float = Field(..., description="Horizontal coordinate in the zone layout")
    y: float = Field(..., description="Vertical coordinate in the zone layout")
    intensity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized intensity value (0.0 = empty, 1.0 = maximum density)",
    )


class Zone(BaseModel):
    """A discrete physical area within the venue."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., min_length=1, description="Unique zone identifier")
    name: str = Field(..., min_length=1, description="Human-readable zone name")
    capacity: int = Field(..., gt=0, description="Maximum safe occupancy")
    adjacent_zones: list[str] = Field(
        default_factory=list,
        description="IDs of directly connected zones for graph traversal",
    )
    is_covered: bool = Field(
        default=False,
        description="Indicates whether the zone is covered/indoors (for rain simulation)",
    )
    heatmap_points: list[IntensityPoint] = Field(
        default_factory=list,
        description="Spatial intensity data for heat-density visualization — populated by preprocessor (Rule C)",
    )


class Occupancy(BaseModel):
    """Point-in-time occupancy reading for a single zone.

    ``pct_capacity`` and ``trend`` are populated by the preprocessor (Rule C).
    Adapters should leave them at their defaults (0.0 and "stable").
    """

    model_config = ConfigDict(frozen=True)

    zone_id: str = Field(..., min_length=1)
    count: int = Field(..., ge=0, description="Current headcount in the zone")
    capacity: int = Field(
        ...,
        gt=0,
        description="Zone capacity at time of reading (snapshot value)",
    )
    pct_capacity: float = Field(
        default=0.0,
        ge=0.0,
        description="Percentage of capacity — computed by preprocessor (Rule C)",
    )
    trend: Literal["rising", "falling", "stable"] = Field(
        default="stable",
        description="Occupancy direction — computed by preprocessor (Rule C)",
    )

    @model_validator(mode="after")
    def _guard_count_within_capacity_bound(self) -> Occupancy:
        """Reject garbage input where count absurdly exceeds capacity.

        A 3× multiplier allows for reasonable over-capacity scenarios
        (standing room, temporary surges) while catching data corruption
        from malformed uploads or sensor glitches.
        """
        max_allowed: int = 3 * self.capacity
        if self.count > max_allowed:
            raise ValueError(
                f"Occupancy count ({self.count}) exceeds 3× capacity "
                f"({self.capacity}) for zone '{self.zone_id}'. "
                f"Maximum allowed: {max_allowed}. This indicates garbage input."
            )
        return self


class Incident(BaseModel):
    """A reported event requiring operational attention."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., min_length=1, description="Unique incident identifier")
    zone_id: str = Field(..., min_length=1)
    type: Literal[
        "medical", "security", "overcrowding", "equipment_failure", "weather"
    ] = Field(..., description="Incident classification")
    severity: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Impact severity level"
    )
    reported_at: datetime = Field(
        ..., description="When the incident was reported (must be tz-aware)"
    )

    @field_validator("reported_at")
    @classmethod
    def _ensure_timezone_aware(cls, v: datetime) -> datetime:
        """Reject naive datetime objects — all timestamps must carry tzinfo."""
        if v.tzinfo is None:
            raise ValueError(
                "reported_at must be timezone-aware. "
                "Received a naive datetime without tzinfo."
            )
        return v


class Staff(BaseModel):
    """A staff member assigned to venue operations."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., min_length=1, description="Unique staff identifier")
    role: Literal["security", "medical", "operations", "hospitality"] = Field(
        ..., description="Staff function"
    )
    zone_id: str = Field(..., min_length=1, description="Currently assigned zone")
    status: Literal["on_duty", "off_duty", "break", "responding"] = Field(
        ..., description="Current operational status"
    )


class HistoricalMetrics(BaseModel):
    """Post-event summary produced after a session concludes.

    Contains aggregated insights for organizer debrief and reporting.
    This model is **not** part of the live VenueSnapshot; it is generated
    by the preprocessor once the event window closes.
    """

    model_config = ConfigDict(frozen=True)

    top_bottlenecks: list[str] = Field(
        ...,
        min_length=1,
        description="Zone IDs or names identified as major congestion points",
    )
    critical_density_duration_minutes: int = Field(
        ...,
        ge=0,
        description="Total minutes any zone exceeded its critical density threshold",
    )
    executive_summary: str = Field(
        ...,
        min_length=1,
        description="Human-readable post-event summary for organizer debrief",
    )


# ---------------------------------------------------------------------------
# Aggregate snapshot
# ---------------------------------------------------------------------------


class VenueSnapshot(BaseModel):
    """Complete point-in-time state of the entire venue.

    This is the top-level canonical data contract.  Every data source adapter
    must produce instances of this model.  The reasoning engine receives only
    VenueSnapshot objects — never raw data (Rule A).
    """

    model_config = ConfigDict(frozen=True)

    timestamp: datetime = Field(
        ..., description="Snapshot capture time (must be tz-aware)"
    )
    zones: list[Zone] = Field(..., min_length=1)
    occupancies: list[Occupancy] = Field(default_factory=list)
    incidents: list[Incident] = Field(default_factory=list)
    staff: list[Staff] = Field(default_factory=list)

    @field_validator("timestamp")
    @classmethod
    def _ensure_timestamp_tz_aware(cls, v: datetime) -> datetime:
        """VenueSnapshot timestamp must be timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("VenueSnapshot.timestamp must be timezone-aware.")
        return v

    @model_validator(mode="after")
    def _cross_validate_zone_references(self) -> VenueSnapshot:
        """Ensure all zone_id references point to zones in this snapshot."""
        valid_ids: frozenset[str] = frozenset(z.id for z in self.zones)

        for occ in self.occupancies:
            if occ.zone_id not in valid_ids:
                raise ValueError(
                    f"Occupancy references unknown zone_id '{occ.zone_id}'. "
                    f"Valid zones: {sorted(valid_ids)}"
                )

        for inc in self.incidents:
            if inc.zone_id not in valid_ids:
                raise ValueError(
                    f"Incident '{inc.id}' references unknown zone_id "
                    f"'{inc.zone_id}'. Valid zones: {sorted(valid_ids)}"
                )

        for s in self.staff:
            if s.zone_id not in valid_ids:
                raise ValueError(
                    f"Staff '{s.id}' references unknown zone_id "
                    f"'{s.zone_id}'. Valid zones: {sorted(valid_ids)}"
                )

        return self
