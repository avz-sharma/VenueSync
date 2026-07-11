"""Tests for Data Source Adapters.

Validates that the SyntheticAdapter produces well-formed, schema-compliant
VenueSnapshot objects with timezone-aware timestamps, monotonically
increasing clocks, and ISO 8601 formatting.

Also verifies the adapter factory and the CustomUploadAdapter stub.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from backend.adapters import get_adapter
from backend.adapters.synthetic import SyntheticAdapter
from backend.adapters.upload import CustomUploadAdapter
from shared.schemas.domain import Occupancy, Staff, VenueSnapshot, Zone

_TZ_IST: ZoneInfo = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# SyntheticAdapter — snapshot generation
# ---------------------------------------------------------------------------


class TestSyntheticAdapterSnapshot:
    """Verify SyntheticAdapter.get_snapshot() produces valid data."""

    @pytest.mark.asyncio
    async def test_returns_venue_snapshot(self) -> None:
        adapter = SyntheticAdapter(seed=42)
        snapshot: VenueSnapshot = await adapter.get_snapshot()
        assert isinstance(snapshot, VenueSnapshot)

    @pytest.mark.asyncio
    async def test_snapshot_has_8_zones(self) -> None:
        adapter = SyntheticAdapter(seed=42)
        snapshot = await adapter.get_snapshot()
        assert len(snapshot.zones) == 8

    @pytest.mark.asyncio
    async def test_snapshot_has_occupancy_for_every_zone(self) -> None:
        adapter = SyntheticAdapter(seed=42)
        snapshot = await adapter.get_snapshot()
        zone_ids: set[str] = {z.id for z in snapshot.zones}
        occ_zone_ids: set[str] = {o.zone_id for o in snapshot.occupancies}
        assert occ_zone_ids == zone_ids

    @pytest.mark.asyncio
    async def test_snapshot_validates_against_pydantic(self) -> None:
        """Prove Rule B compliance: output validates against schema."""
        adapter = SyntheticAdapter(seed=42)
        snapshot = await adapter.get_snapshot()
        # Re-validate from dict round-trip
        revalidated: VenueSnapshot = VenueSnapshot.model_validate(snapshot.model_dump())
        assert revalidated.timestamp == snapshot.timestamp

    @pytest.mark.asyncio
    async def test_occupancy_pct_capacity_defaults_to_zero(self) -> None:
        """pct_capacity must be 0.0 — preprocessor is responsible (Rule C)."""
        adapter = SyntheticAdapter(seed=42)
        snapshot = await adapter.get_snapshot()
        for occ in snapshot.occupancies:
            assert occ.pct_capacity == 0.0

    @pytest.mark.asyncio
    async def test_occupancy_count_within_capacity_bounds(self) -> None:
        """No occupancy should exceed the zone capacity (factor clamped to 1.0)."""
        adapter = SyntheticAdapter(seed=42)
        for _ in range(10):  # run through several ticks
            snapshot = await adapter.get_snapshot()
            for occ in snapshot.occupancies:
                assert 0 <= occ.count <= occ.capacity


# ---------------------------------------------------------------------------
# SyntheticAdapter — timezone and clock
# ---------------------------------------------------------------------------


class TestSyntheticAdapterTimezone:
    """Verify timezone-awareness and clock advancement."""

    @pytest.mark.asyncio
    async def test_timestamp_is_timezone_aware(self) -> None:
        adapter = SyntheticAdapter(seed=42)
        snapshot = await adapter.get_snapshot()
        assert snapshot.timestamp.tzinfo is not None

    @pytest.mark.asyncio
    async def test_timestamp_uses_asia_kolkata(self) -> None:
        adapter = SyntheticAdapter(seed=42)
        snapshot = await adapter.get_snapshot()
        # ZoneInfo comparison via UTC offset for IST (+05:30)
        utc_offset = snapshot.timestamp.utcoffset()
        assert utc_offset is not None
        total_minutes: float = utc_offset.total_seconds() / 60
        assert total_minutes == 330  # 5h30m = 330 minutes

    @pytest.mark.asyncio
    async def test_iso8601_format_includes_offset(self) -> None:
        adapter = SyntheticAdapter(seed=42)
        snapshot = await adapter.get_snapshot()
        iso_str: str = snapshot.timestamp.isoformat()
        assert "+05:30" in iso_str

    @pytest.mark.asyncio
    async def test_sequential_timestamps_are_monotonically_increasing(self) -> None:
        adapter = SyntheticAdapter(seed=42)
        snap1 = await adapter.get_snapshot()
        snap2 = await adapter.get_snapshot()
        snap3 = await adapter.get_snapshot()
        assert snap1.timestamp < snap2.timestamp < snap3.timestamp

    @pytest.mark.asyncio
    async def test_timestamp_advances_by_tick_minutes(self) -> None:
        tick_minutes: int = 5
        adapter = SyntheticAdapter(seed=42, tick_minutes=tick_minutes)
        snap1 = await adapter.get_snapshot()
        snap2 = await adapter.get_snapshot()
        delta = snap2.timestamp - snap1.timestamp
        assert delta.total_seconds() == tick_minutes * 60

    @pytest.mark.asyncio
    async def test_incident_timestamps_are_timezone_aware(self) -> None:
        """All incident reported_at must carry tzinfo."""
        adapter = SyntheticAdapter(seed=42)
        # Run enough ticks to generate incidents
        for _ in range(20):
            snapshot = await adapter.get_snapshot()
            for inc in snapshot.incidents:
                assert inc.reported_at.tzinfo is not None


# ---------------------------------------------------------------------------
# SyntheticAdapter — venue graph and staff roster
# ---------------------------------------------------------------------------


class TestSyntheticAdapterGraph:
    """Verify get_venue_graph() and get_staff_roster()."""

    @pytest.mark.asyncio
    async def test_venue_graph_returns_zones(self) -> None:
        adapter = SyntheticAdapter(seed=42)
        zones: list[Zone] = await adapter.get_venue_graph()
        assert len(zones) == 8
        assert all(isinstance(z, Zone) for z in zones)

    @pytest.mark.asyncio
    async def test_zones_have_adjacency_info(self) -> None:
        adapter = SyntheticAdapter(seed=42)
        zones = await adapter.get_venue_graph()
        # At least some zones should have adjacent zones defined
        zones_with_adj = [z for z in zones if len(z.adjacent_zones) > 0]
        assert len(zones_with_adj) > 0

    @pytest.mark.asyncio
    async def test_adjacency_references_valid_zones(self) -> None:
        adapter = SyntheticAdapter(seed=42)
        zones = await adapter.get_venue_graph()
        valid_ids: set[str] = {z.id for z in zones}
        for z in zones:
            for adj in z.adjacent_zones:
                assert (
                    adj in valid_ids
                ), f"Zone '{z.id}' references unknown adjacent zone '{adj}'"

    @pytest.mark.asyncio
    async def test_staff_roster_returns_staff(self) -> None:
        adapter = SyntheticAdapter(seed=42)
        staff: list[Staff] = await adapter.get_staff_roster()
        assert len(staff) > 0
        assert all(isinstance(s, Staff) for s in staff)


# ---------------------------------------------------------------------------
# SyntheticAdapter — deterministic seeding
# ---------------------------------------------------------------------------


class TestSyntheticAdapterDeterminism:
    """Verify that the same seed produces the same data."""

    @pytest.mark.asyncio
    async def test_same_seed_same_output(self) -> None:
        adapter_a = SyntheticAdapter(seed=123)
        adapter_b = SyntheticAdapter(seed=123)
        snap_a = await adapter_a.get_snapshot()
        snap_b = await adapter_b.get_snapshot()
        # Timestamps should match
        assert snap_a.timestamp == snap_b.timestamp
        # Occupancy counts should match
        counts_a = {o.zone_id: o.count for o in snap_a.occupancies}
        counts_b = {o.zone_id: o.count for o in snap_b.occupancies}
        assert counts_a == counts_b

    @pytest.mark.asyncio
    async def test_different_seed_different_output(self) -> None:
        adapter_a = SyntheticAdapter(seed=1)
        adapter_b = SyntheticAdapter(seed=999)
        snap_a = await adapter_a.get_snapshot()
        snap_b = await adapter_b.get_snapshot()
        # Same timestamps (clock is seed-independent) but different counts
        counts_a = {o.zone_id: o.count for o in snap_a.occupancies}
        counts_b = {o.zone_id: o.count for o in snap_b.occupancies}
        assert counts_a != counts_b


# ---------------------------------------------------------------------------
# CustomUploadAdapter — stub verification
# ---------------------------------------------------------------------------


class TestCustomUploadAdapter:
    """Verify that stubbed methods raise NotImplementedError."""

    @pytest.mark.asyncio
    async def test_get_snapshot_raises(self) -> None:
        adapter = CustomUploadAdapter()
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await adapter.get_snapshot()

    @pytest.mark.asyncio
    async def test_get_venue_graph_raises(self) -> None:
        adapter = CustomUploadAdapter()
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await adapter.get_venue_graph()

    @pytest.mark.asyncio
    async def test_get_staff_roster_raises(self) -> None:
        adapter = CustomUploadAdapter()
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await adapter.get_staff_roster()


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


class TestAdapterFactory:
    """Verify the get_adapter() factory function."""

    def test_synthetic_returns_synthetic_adapter(self) -> None:
        adapter = get_adapter("synthetic")
        assert isinstance(adapter, SyntheticAdapter)

    def test_upload_returns_upload_adapter(self) -> None:
        adapter = get_adapter("upload")
        assert isinstance(adapter, CustomUploadAdapter)

    def test_unknown_source_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown data source"):
            get_adapter("nonexistent")
