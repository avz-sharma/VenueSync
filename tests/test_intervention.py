"""Tests for the preprocessor intervention logic (Rule C compliance)."""

import pytest

from backend.preprocessor.intervention import (
    InterventionStateManager,
    blend_occupancy,
    compute_alpha,
    compute_gate_closure_targets,
    compute_rain_shift_targets,
)
from shared.schemas.domain import Occupancy, Zone


def test_compute_alpha():
    """Alpha should be clamped between 0.0 and 1.0 based on elapsed time."""
    assert compute_alpha(approved_at=100.0, now=90.0, duration=10.0) == 0.0
    assert compute_alpha(approved_at=100.0, now=100.0, duration=10.0) == 0.0
    assert compute_alpha(approved_at=100.0, now=105.0, duration=10.0) == 0.5
    assert compute_alpha(approved_at=100.0, now=110.0, duration=10.0) == 1.0
    assert compute_alpha(approved_at=100.0, now=120.0, duration=10.0) == 1.0

    # Zero or negative duration instantly completes
    assert compute_alpha(approved_at=100.0, now=101.0, duration=0.0) == 1.0


def test_blend_occupancy():
    """Occupancy should be linearly interpolated and rounded."""
    assert blend_occupancy(source=100, target=200, alpha=0.0) == 100
    assert blend_occupancy(source=100, target=200, alpha=0.5) == 150
    assert blend_occupancy(source=100, target=200, alpha=1.0) == 200

    # Check rounding
    assert blend_occupancy(source=10, target=20, alpha=0.1) == 11  # 10 + 1
    assert blend_occupancy(source=10, target=20, alpha=0.15) == 12  # 10 + 1.5 -> 12


@pytest.fixture
def sample_zones():
    return [
        Zone(id="gate_north", name="Gate North", capacity=2000),
        Zone(id="gate_south", name="Gate South", capacity=2000),
        Zone(id="concourse_a", name="Concourse A", capacity=3000, is_covered=True),
        Zone(id="stand_east", name="Stand East", capacity=5000),
    ]


@pytest.fixture
def sample_occupancies():
    return [
        Occupancy(zone_id="gate_north", count=1000, capacity=2000),
        Occupancy(zone_id="gate_south", count=500, capacity=2000),
        Occupancy(zone_id="concourse_a", count=1000, capacity=3000),
        Occupancy(zone_id="stand_east", count=4000, capacity=5000),
    ]


def test_compute_gate_closure_targets(sample_zones, sample_occupancies):
    """Gate closure should distribute crowd to alternatives."""
    targets = compute_gate_closure_targets(
        sample_zones, sample_occupancies, "gate_north"
    )

    assert targets["gate_north"] == 0

    # 1000 people from gate_north redistributed evenly to gate_south and concourse_a
    # That's 500 each.
    # gate_south: 500 + 500 = 1000
    # concourse_a: 1000 + 500 = 1500
    # stand_east: unchanged (4000)

    assert targets["gate_south"] == 1000
    assert targets["concourse_a"] == 1500
    assert targets["stand_east"] == 4000

    # Total headcount conserved
    original_total = sum(o.count for o in sample_occupancies)
    new_total = sum(targets.values())
    assert original_total == new_total


def test_compute_rain_shift_targets(sample_zones, sample_occupancies):
    """Rain shift should move crowd from exposed to covered zones."""
    targets = compute_rain_shift_targets(sample_zones, sample_occupancies)

    # Covered zones: concourse_a
    # Exposed zones: gate_north, gate_south, stand_east

    # Original exposed: 1000 (gate_north) + 500 (gate_south) + 4000 (stand_east)
    # 50% shift means:
    # gate_north loses 500
    # gate_south loses 250
    # stand_east loses 2000
    # Total shifted = 2750

    assert targets["gate_north"] == 500
    assert targets["gate_south"] == 250
    assert targets["stand_east"] == 2000

    # concourse_a gets the full 2750 shifted
    assert targets["concourse_a"] == 1000 + 2750

    # Total headcount conserved
    original_total = sum(o.count for o in sample_occupancies)
    new_total = sum(targets.values())
    assert original_total == new_total


def test_intervention_state_manager():
    """State manager should correctly handle the lifecycle."""
    source = {"z1": 100, "z2": 200}
    target = {"z1": 0, "z2": 300}

    mgr = InterventionStateManager(
        approved_at=10.0,
        source_occupancies=source,
        target_occupancies=target,
        duration=10.0,
    )

    # Before
    b1 = mgr.get_blended_occupancies(5.0)
    assert b1["z1"] == 100
    assert b1["z2"] == 200
    assert not mgr.is_complete(5.0)

    # Halfway
    b2 = mgr.get_blended_occupancies(15.0)
    assert b2["z1"] == 50
    assert b2["z2"] == 250
    assert not mgr.is_complete(15.0)

    # Complete
    b3 = mgr.get_blended_occupancies(20.0)
    assert b3["z1"] == 0
    assert b3["z2"] == 300
    assert mgr.is_complete(20.0)

    # After
    b4 = mgr.get_blended_occupancies(25.0)
    assert b4["z1"] == 0
    assert b4["z2"] == 300
    assert mgr.is_complete(25.0)
