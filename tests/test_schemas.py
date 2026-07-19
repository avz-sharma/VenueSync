"""Tests for the Canonical Data Schema (shared.schemas.domain).

Validates Pydantic v2 model construction, field constraints, model validators,
and cross-model reference integrity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from shared.schemas.domain import (
    HistoricalMetrics,
    Incident,
    IntensityPoint,
    Occupancy,
    Staff,
    VenueSnapshot,
    Zone,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TZ_IST: ZoneInfo = ZoneInfo("Asia/Kolkata")
_NOW: datetime = datetime.now(_TZ_IST)


def _make_zone(
    zone_id: str = "zone_a",
    name: str = "Zone A",
    capacity: int = 1000,
    adjacent: list[str] | None = None,
) -> Zone:
    return Zone(
        id=zone_id,
        name=name,
        capacity=capacity,
        adjacent_zones=adjacent or [],
    )


def _make_occupancy(
    zone_id: str = "zone_a",
    count: int = 500,
    capacity: int = 1000,
) -> Occupancy:
    return Occupancy(zone_id=zone_id, count=count, capacity=capacity)


def _make_incident(
    incident_id: str = "inc_001",
    zone_id: str = "zone_a",
    reported_at: datetime | None = None,
) -> Incident:
    return Incident(
        id=incident_id,
        zone_id=zone_id,
        type="security",
        severity="medium",
        reported_at=reported_at or _NOW,
    )


def _make_staff(
    staff_id: str = "staff_001",
    zone_id: str = "zone_a",
) -> Staff:
    return Staff(
        id=staff_id,
        role="security",
        zone_id=zone_id,
        status="on_duty",
    )


# ---------------------------------------------------------------------------
# Zone tests
# ---------------------------------------------------------------------------


class TestZone:
    """Tests for the Zone model."""

    def test_valid_construction(self) -> None:
        zone = _make_zone()
        assert zone.id == "zone_a"
        assert zone.name == "Zone A"
        assert zone.capacity == 1000
        assert zone.adjacent_zones == []

    def test_with_adjacent_zones(self) -> None:
        zone = _make_zone(adjacent=["zone_b", "zone_c"])
        assert zone.adjacent_zones == ["zone_b", "zone_c"]

    def test_rejects_zero_capacity(self) -> None:
        with pytest.raises(ValidationError, match="greater than 0"):
            _make_zone(capacity=0)

    def test_rejects_negative_capacity(self) -> None:
        with pytest.raises(ValidationError, match="greater than 0"):
            _make_zone(capacity=-100)

    def test_rejects_empty_id(self) -> None:
        with pytest.raises(ValidationError, match="at least 1"):
            _make_zone(zone_id="")

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValidationError, match="at least 1"):
            _make_zone(name="")

    def test_frozen(self) -> None:
        zone = _make_zone()
        with pytest.raises(ValidationError):
            setattr(zone, "capacity", 2000)


# ---------------------------------------------------------------------------
# Occupancy tests
# ---------------------------------------------------------------------------


class TestOccupancy:
    """Tests for the Occupancy model and its 3× capacity guardrail."""

    def test_valid_construction(self) -> None:
        occ = _make_occupancy(count=500, capacity=1000)
        assert occ.zone_id == "zone_a"
        assert occ.count == 500
        assert occ.capacity == 1000

    def test_defaults_pct_capacity_to_zero(self) -> None:
        """pct_capacity must default to 0.0 — preprocessor computes it."""
        occ = _make_occupancy()
        assert occ.pct_capacity == 0.0

    def test_defaults_trend_to_stable(self) -> None:
        """trend must default to 'stable' — preprocessor computes it."""
        occ = _make_occupancy()
        assert occ.trend == "stable"

    def test_accepts_count_at_capacity(self) -> None:
        occ = _make_occupancy(count=1000, capacity=1000)
        assert occ.count == 1000

    def test_accepts_count_up_to_3x_capacity(self) -> None:
        """Allow reasonable over-capacity (surge, standing room)."""
        occ = _make_occupancy(count=3000, capacity=1000)
        assert occ.count == 3000

    def test_rejects_count_exceeding_3x_capacity(self) -> None:
        """Count > 3× capacity indicates garbage input."""
        with pytest.raises(ValidationError, match="3× capacity"):
            _make_occupancy(count=3001, capacity=1000)

    def test_rejects_negative_count(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            _make_occupancy(count=-1)

    def test_rejects_zero_capacity(self) -> None:
        with pytest.raises(ValidationError, match="greater than 0"):
            _make_occupancy(capacity=0)

    def test_frozen(self) -> None:
        occ = _make_occupancy()
        with pytest.raises(ValidationError):
            setattr(occ, "count", 999)


# ---------------------------------------------------------------------------
# Incident tests
# ---------------------------------------------------------------------------


class TestIncident:
    """Tests for the Incident model and timezone-awareness validation."""

    def test_valid_construction(self) -> None:
        inc = _make_incident()
        assert inc.id == "inc_001"
        assert inc.type == "security"
        assert inc.severity == "medium"

    def test_reported_at_is_tz_aware(self) -> None:
        inc = _make_incident(reported_at=_NOW)
        assert inc.reported_at.tzinfo is not None

    def test_rejects_naive_reported_at(self) -> None:
        """Naive datetime (no tzinfo) must be rejected."""
        naive_dt: datetime = datetime(2026, 7, 10, 18, 0, 0)
        with pytest.raises(ValidationError, match="timezone-aware"):
            _make_incident(reported_at=naive_dt)

    def test_accepts_utc_reported_at(self) -> None:
        utc_dt: datetime = datetime(2026, 7, 10, 12, 30, 0, tzinfo=timezone.utc)
        inc = _make_incident(reported_at=utc_dt)
        assert inc.reported_at.tzinfo == timezone.utc

    def test_accepts_ist_reported_at(self) -> None:
        ist_dt: datetime = datetime(2026, 7, 10, 18, 0, 0, tzinfo=_TZ_IST)
        inc = _make_incident(reported_at=ist_dt)
        assert inc.reported_at.tzinfo is not None

    def test_all_incident_types(self) -> None:
        valid_types = [
            "medical",
            "security",
            "overcrowding",
            "equipment_failure",
            "weather",
        ]
        for t in valid_types:
            inc = Incident(
                id="inc_t",
                zone_id="zone_a",
                type=t,
                severity="low",
                reported_at=_NOW,
            )
            assert inc.type == t

    def test_rejects_invalid_type(self) -> None:
        with pytest.raises(ValidationError):
            Incident(
                **{
                    "id": "inc_bad",
                    "zone_id": "zone_a",
                    "type": "fire",
                    "severity": "low",
                    "reported_at": _NOW,
                }
            )

    def test_all_severities(self) -> None:
        for sev in ["low", "medium", "high", "critical"]:
            inc = Incident(
                id="inc_s",
                zone_id="zone_a",
                type="medical",
                severity=sev,
                reported_at=_NOW,
            )
            assert inc.severity == sev


# ---------------------------------------------------------------------------
# Staff tests
# ---------------------------------------------------------------------------


class TestStaff:
    """Tests for the Staff model."""

    def test_valid_construction(self) -> None:
        staff = _make_staff()
        assert staff.id == "staff_001"
        assert staff.role == "security"
        assert staff.status == "on_duty"

    def test_all_roles(self) -> None:
        for role in ["security", "medical", "operations", "hospitality"]:
            s = Staff(id="s1", role=role, zone_id="z1", status="on_duty")
            assert s.role == role

    def test_all_statuses(self) -> None:
        for status in ["on_duty", "off_duty", "break", "responding"]:
            s = Staff(id="s1", role="security", zone_id="z1", status=status)
            assert s.status == status

    def test_rejects_invalid_role(self) -> None:
        with pytest.raises(ValidationError):
            Staff(
                **{
                    "id": "s1",
                    "role": "janitor",
                    "zone_id": "z1",
                    "status": "on_duty",
                }
            )


# ---------------------------------------------------------------------------
# VenueSnapshot tests
# ---------------------------------------------------------------------------


class TestVenueSnapshot:
    """Tests for the VenueSnapshot aggregate and its cross-validators."""

    def _make_snapshot(
        self,
        zones: list[Zone] | None = None,
        occupancies: list[Occupancy] | None = None,
        incidents: list[Incident] | None = None,
        staff: list[Staff] | None = None,
        timestamp: datetime | None = None,
    ) -> VenueSnapshot:
        return VenueSnapshot(
            timestamp=timestamp if timestamp is not None else _NOW,
            zones=[_make_zone()] if zones is None else zones,
            occupancies=occupancies if occupancies is not None else [],
            incidents=incidents if incidents is not None else [],
            staff=staff if staff is not None else [],
        )

    def test_valid_construction(self) -> None:
        snap = self._make_snapshot()
        assert snap.timestamp.tzinfo is not None
        assert len(snap.zones) == 1

    def test_rejects_naive_timestamp(self) -> None:
        naive_ts: datetime = datetime(2026, 7, 10, 18, 0, 0)
        with pytest.raises(ValidationError, match="timezone-aware"):
            self._make_snapshot(timestamp=naive_ts)

    def test_rejects_empty_zones(self) -> None:
        with pytest.raises(ValidationError):
            self._make_snapshot(zones=[])

    def test_valid_occupancy_reference(self) -> None:
        zone = _make_zone(zone_id="z1")
        occ = _make_occupancy(zone_id="z1")
        snap = self._make_snapshot(zones=[zone], occupancies=[occ])
        assert len(snap.occupancies) == 1

    def test_rejects_dangling_occupancy_zone_id(self) -> None:
        zone = _make_zone(zone_id="z1")
        occ = _make_occupancy(zone_id="nonexistent")
        with pytest.raises(ValidationError, match="unknown zone_id"):
            self._make_snapshot(zones=[zone], occupancies=[occ])

    def test_rejects_dangling_incident_zone_id(self) -> None:
        zone = _make_zone(zone_id="z1")
        inc = _make_incident(zone_id="nonexistent")
        with pytest.raises(ValidationError, match="unknown zone_id"):
            self._make_snapshot(zones=[zone], incidents=[inc])

    def test_rejects_dangling_staff_zone_id(self) -> None:
        zone = _make_zone(zone_id="z1")
        staff = _make_staff(zone_id="nonexistent")
        with pytest.raises(ValidationError, match="unknown zone_id"):
            self._make_snapshot(zones=[zone], staff=[staff])

    def test_all_references_valid(self) -> None:
        zone = _make_zone(zone_id="z1")
        occ = _make_occupancy(zone_id="z1")
        inc = _make_incident(zone_id="z1")
        staff = _make_staff(zone_id="z1")
        snap = self._make_snapshot(
            zones=[zone], occupancies=[occ], incidents=[inc], staff=[staff]
        )
        assert len(snap.zones) == 1
        assert len(snap.occupancies) == 1
        assert len(snap.incidents) == 1
        assert len(snap.staff) == 1

    def test_frozen(self) -> None:
        snap = self._make_snapshot()
        with pytest.raises(ValidationError):
            setattr(snap, "timestamp", _NOW)


# ---------------------------------------------------------------------------
# IntensityPoint tests
# ---------------------------------------------------------------------------


class TestIntensityPoint:
    """Tests for the IntensityPoint spatial data model."""

    def test_valid_construction(self) -> None:
        pt = IntensityPoint(x=10.5, y=20.3, intensity=0.75)
        assert pt.x == 10.5
        assert pt.y == 20.3
        assert pt.intensity == 0.75

    def test_boundary_intensity_zero(self) -> None:
        pt = IntensityPoint(x=0.0, y=0.0, intensity=0.0)
        assert pt.intensity == 0.0

    def test_boundary_intensity_one(self) -> None:
        pt = IntensityPoint(x=0.0, y=0.0, intensity=1.0)
        assert pt.intensity == 1.0

    def test_rejects_intensity_below_zero(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            IntensityPoint(x=0.0, y=0.0, intensity=-0.1)

    def test_rejects_intensity_above_one(self) -> None:
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            IntensityPoint(x=0.0, y=0.0, intensity=1.01)

    def test_accepts_negative_coordinates(self) -> None:
        """Coordinates can be negative — layout origin is flexible."""
        pt = IntensityPoint(x=-5.0, y=-10.0, intensity=0.5)
        assert pt.x == -5.0
        assert pt.y == -10.0

    def test_frozen(self) -> None:
        pt = IntensityPoint(x=1.0, y=2.0, intensity=0.5)
        with pytest.raises(ValidationError):
            setattr(pt, "intensity", 0.9)


# ---------------------------------------------------------------------------
# Zone heatmap_points tests
# ---------------------------------------------------------------------------


class TestZoneHeatmapPoints:
    """Tests for the optional heatmap_points field on Zone."""

    def test_defaults_to_empty_list(self) -> None:
        zone = _make_zone()
        assert zone.heatmap_points == []

    def test_accepts_heatmap_points(self) -> None:
        points = [
            IntensityPoint(x=0.0, y=0.0, intensity=0.1),
            IntensityPoint(x=5.0, y=5.0, intensity=0.9),
        ]
        zone = Zone(
            id="z1",
            name="Zone 1",
            capacity=500,
            heatmap_points=points,
        )
        assert len(zone.heatmap_points) == 2
        assert zone.heatmap_points[0].intensity == 0.1
        assert zone.heatmap_points[1].intensity == 0.9

    def test_rejects_invalid_heatmap_point(self) -> None:
        """IntensityPoint validation still fires when nested in Zone."""
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            Zone(
                id="z1",
                name="Zone 1",
                capacity=500,
                heatmap_points=[
                    IntensityPoint(x=0.0, y=0.0, intensity=-0.5),
                ],
            )


# ---------------------------------------------------------------------------
# HistoricalMetrics tests
# ---------------------------------------------------------------------------


class TestHistoricalMetrics:
    """Tests for the HistoricalMetrics post-event summary model."""

    def test_valid_construction(self) -> None:
        hm = HistoricalMetrics(
            top_bottlenecks=["zone_a", "zone_c"],
            critical_density_duration_minutes=42,
            executive_summary="Peak congestion at Gate B during halftime.",
        )
        assert hm.top_bottlenecks == ["zone_a", "zone_c"]
        assert hm.critical_density_duration_minutes == 42
        assert "Gate B" in hm.executive_summary

    def test_rejects_empty_top_bottlenecks(self) -> None:
        with pytest.raises(ValidationError):
            HistoricalMetrics(
                top_bottlenecks=[],
                critical_density_duration_minutes=10,
                executive_summary="Summary.",
            )

    def test_rejects_negative_duration(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            HistoricalMetrics(
                top_bottlenecks=["zone_a"],
                critical_density_duration_minutes=-1,
                executive_summary="Summary.",
            )

    def test_accepts_zero_duration(self) -> None:
        hm = HistoricalMetrics(
            top_bottlenecks=["zone_a"],
            critical_density_duration_minutes=0,
            executive_summary="No critical density events.",
        )
        assert hm.critical_density_duration_minutes == 0

    def test_rejects_empty_executive_summary(self) -> None:
        with pytest.raises(ValidationError, match="at least 1"):
            HistoricalMetrics(
                top_bottlenecks=["zone_a"],
                critical_density_duration_minutes=10,
                executive_summary="",
            )

    def test_frozen(self) -> None:
        hm = HistoricalMetrics(
            top_bottlenecks=["zone_a"],
            critical_density_duration_minutes=10,
            executive_summary="Summary.",
        )
        with pytest.raises(ValidationError):
            setattr(hm, "critical_density_duration_minutes", 99)
