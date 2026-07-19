from __future__ import annotations

from backend.schemas import VenueSnapshot


def _compute_pct_capacity(count: int, capacity: int) -> float:
    """Helper to deterministically calculate percentage capacity."""
    return (count / capacity * 100.0) if capacity > 0 else 0.0


def preprocess_snapshot(snapshot: VenueSnapshot) -> dict:
    """
    Deterministically processes the raw venue snapshot to compute occupancies,
    rates of change, and threshold breaches.
    """
    processed_zones = []
    zone_names = {zone.id: zone.name for zone in snapshot.zones}

    for occ in snapshot.occupancies:
        pct_capacity = _compute_pct_capacity(occ.count, occ.capacity)

        processed_zones.append(
            {
                "zone_id": occ.zone_id,
                "zone_name": zone_names.get(occ.zone_id, occ.zone_id),
                "pct_capacity": round(pct_capacity, 2),
                "trend": occ.trend,
                "is_critical": pct_capacity > 95.0,
                "has_spare_capacity": pct_capacity < 60.0,
            }
        )

    processed_incidents = [
        {
            "id": inc.id,
            "zone_id": inc.zone_id,
            "type": inc.type,
            "severity": inc.severity,
        }
        for inc in snapshot.incidents
    ]
    return {"zones": processed_zones, "incidents": processed_incidents}


# ---------------------------------------------------------------------------
# Historical run aggregation (Rule C — deterministic math only)
# ---------------------------------------------------------------------------

_POLLING_INTERVAL_MINUTES: int = 5
"""Assumed polling cadence between snapshots, in minutes.

Every snapshot in a run sequence represents one polling tick. Multiplying
the total breach-tick count by this constant converts ticks → minutes spent
at critical density.  Changing the cadence here is the *only* place it
needs to change — the LLM never sees or derives this number.
"""

_CRITICAL_PCT_THRESHOLD: float = 95.0
"""PHS critical density threshold expressed as a percentage of capacity.

Maps to > 4.0 PPL/m² in the PHS standard.  Zone occupancy exceeding this
value for any snapshot tick counts as one breach-tick for that zone.
"""

_TOP_BOTTLENECK_COUNT: int = 3
"""Maximum number of bottleneck zones reported in the summary."""


def process_historical_run(snapshots: list[VenueSnapshot]) -> dict:
    """Deterministically aggregate a completed run sequence into compressed metrics.
    Implements Rule C — all arithmetic is isolated here.
    """
    zone_breach_ticks: dict[str, int] = {}
    zone_name_lookup: dict[str, str] = {}

    for snapshot in snapshots:
        for zone in snapshot.zones:
            zone_name_lookup[zone.id] = zone.name

        for occ in snapshot.occupancies:
            pct_capacity = _compute_pct_capacity(occ.count, occ.capacity)
            if pct_capacity > 95.0:
                zone_breach_ticks[occ.zone_id] = (
                    zone_breach_ticks.get(occ.zone_id, 0) + 1
                )

    sorted_breaches = sorted(
        zone_breach_ticks.items(), key=lambda item: item[1], reverse=True
    )[:3]

    top_bottleneck_names = [
        zone_name_lookup.get(z_id, z_id) for z_id, _ in sorted_breaches
    ]
    total_breach_ticks = sum(zone_breach_ticks.values())

    return {
        "top_bottlenecks": top_bottleneck_names,
        "critical_density_duration_minutes": total_breach_ticks * 5,
        "snapshot_count": len(snapshots),
    }


# ---------------------------------------------------------------------------
# Predictive Pre-Alert scoring (Rule C — deterministic math only)
# ---------------------------------------------------------------------------

_PRE_ALERT_THRESHOLD: float = 80.0
"""Zones above this percentage AND trending upward trigger a pre-alert evaluation."""

_TREND_VELOCITY: dict[str, float] = {
    "rising": 3.0,
    "stable": 0.0,
    "falling": -2.0,
}
"""Approximate percentage-points-per-tick shift implied by each trend label.

These are deterministic constants — the LLM never sees or derives them.
The values are calibrated for the 5-minute polling interval.
"""


def compute_pre_alert_zones(snapshot: VenueSnapshot) -> list[dict]:
    """Identify zones approaching critical density and compute trajectory metrics.

    Implements Rule C — all arithmetic is isolated here.  The returned list
    of dicts is safe to hand to the Pre-Alert LLM reasoning module as context.

    Algorithm:
      1. For each occupancy, compute ``pct_capacity`` deterministically.
      2. Compute ``trajectory_score = pct_capacity + trend_velocity``.
      3. If ``pct_capacity >= _PRE_ALERT_THRESHOLD`` AND ``trend == "rising"``,
         the zone qualifies for a pre-alert.
      4. Estimate minutes to critical:
         ``max(0, ceil((_CRITICAL_PCT_THRESHOLD - pct_capacity) / velocity * _POLLING_INTERVAL_MINUTES))``.

    Args:
        snapshot: Current canonical VenueSnapshot.

    Returns:
        A list of dicts, each containing:
          - ``zone_id``, ``zone_name``, ``pct_capacity``, ``trend``
          - ``trajectory_score``: float, projected next-tick occupancy percentage
          - ``estimated_minutes_to_critical``: int, how many minutes until breach
          - ``risk_level``: str, one of "elevated" / "high" / "imminent"
    """
    import math

    zone_names = {zone.id: zone.name for zone in snapshot.zones}
    pre_alert_zones: list[dict] = []

    for occ in snapshot.occupancies:
        capacity = occ.capacity
        count = occ.count
        pct_capacity = (count / capacity * 100.0) if capacity > 0 else 0.0
        velocity = _TREND_VELOCITY.get(occ.trend, 0.0)
        trajectory_score = pct_capacity + velocity

        # Only flag zones that are above the pre-alert threshold AND rising
        if pct_capacity >= _PRE_ALERT_THRESHOLD and occ.trend == "rising":
            # Estimate minutes to critical breach
            gap = _CRITICAL_PCT_THRESHOLD - pct_capacity
            if velocity > 0:
                ticks_to_critical = math.ceil(gap / velocity)
                est_minutes = max(0, ticks_to_critical * _POLLING_INTERVAL_MINUTES)
            else:
                est_minutes = 0  # Already above or velocity non-positive

            # Classify risk level deterministically
            if pct_capacity >= 92.0:
                risk_level = "imminent"
            elif pct_capacity >= 87.0:
                risk_level = "high"
            else:
                risk_level = "elevated"

            pre_alert_zones.append(
                {
                    "zone_id": occ.zone_id,
                    "zone_name": zone_names.get(occ.zone_id, occ.zone_id),
                    "pct_capacity": round(pct_capacity, 2),
                    "trend": occ.trend,
                    "trajectory_score": round(trajectory_score, 2),
                    "estimated_minutes_to_critical": est_minutes,
                    "risk_level": risk_level,
                }
            )

    # Sort by risk severity: imminent > high > elevated, then by pct_capacity descending
    risk_order = {"imminent": 0, "high": 1, "elevated": 2}
    pre_alert_zones.sort(
        key=lambda z: (risk_order.get(z["risk_level"], 3), -z["pct_capacity"])
    )

    return pre_alert_zones
