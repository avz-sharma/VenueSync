from __future__ import annotations

from backend.schemas import VenueSnapshot


def preprocess_snapshot(snapshot: VenueSnapshot) -> dict:
    """
    Deterministically processes the raw venue snapshot to compute occupancies,
    rates of change, and threshold breaches. Strips out raw counts and inert
    data to minimize the token payload sent to the LLM.
    """
    processed_zones = []

    zone_names = {zone.id: zone.name for zone in snapshot.zones}

    for occ in snapshot.occupancies:
        zone_id = occ.zone_id
        capacity = occ.capacity
        count = occ.count

        pct_capacity = (count / capacity * 100.0) if capacity > 0 else 0.0

        # Deterministic boolean flags
        is_critical = pct_capacity > 95.0
        has_spare_capacity = pct_capacity < 60.0

        processed_zones.append(
            {
                "zone_id": zone_id,
                "zone_name": zone_names.get(zone_id, zone_id),
                "pct_capacity": round(pct_capacity, 2),
                "trend": occ.trend,
                "is_critical": is_critical,
                "has_spare_capacity": has_spare_capacity,
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

    Implements Rule C — all arithmetic is isolated here and the result is a
    plain dict that is safe to hand to the LLM context.  No model call is
    made inside this function.

    Algorithm (matches the reference sketch at gemini-code-1783928865455.py):
      1. Walk every snapshot.
      2. For each snapshot, build a zone_id → zone_name lookup from snapshot.zones.
      3. Inspect every Occupancy in snapshot.occupancies; if pct_capacity > 95 %
         increment that zone's breach-tick counter.
      4. After all snapshots, multiply total breach ticks by the polling interval
         to obtain critical_density_duration_minutes.
      5. Sort zones by breach-tick count descending; take the top-N names.

    Args:
        snapshots: Ordered list of VenueSnapshot objects representing a full
                   event session.  Must not be empty (validated by the caller).

    Returns:
        A dict with keys:
          - ``top_bottlenecks``: list[str] of zone names, worst first.
          - ``critical_density_duration_minutes``: int, total zone-minutes
            spent above the critical threshold across the entire run.
          - ``snapshot_count``: int, number of snapshots processed (audit trail).
    """
    # zone_id → accumulated breach tick count
    zone_breach_ticks: dict[str, int] = {}
    # zone_id → human-readable name (last seen wins — names are stable)
    zone_name_lookup: dict[str, str] = {}

    for snapshot in snapshots:
        # Build / refresh the id → name map for this snapshot's zone topology
        for zone in snapshot.zones:
            zone_name_lookup[zone.id] = zone.name

        for occ in snapshot.occupancies:
            capacity = occ.capacity
            count = occ.count

            # Deterministic pct_capacity — mirrors preprocess_snapshot (Rule C)
            pct_capacity = (count / capacity * 100.0) if capacity > 0 else 0.0

            if pct_capacity > _CRITICAL_PCT_THRESHOLD:
                zone_breach_ticks[occ.zone_id] = (
                    zone_breach_ticks.get(occ.zone_id, 0) + 1
                )

    # Sort by breach-tick count descending, pick top N
    sorted_breaches = sorted(
        zone_breach_ticks.items(), key=lambda item: item[1], reverse=True
    )[:_TOP_BOTTLENECK_COUNT]

    top_bottleneck_names: list[str] = [
        zone_name_lookup.get(zone_id, zone_id) for zone_id, _ in sorted_breaches
    ]

    # Total zone-minutes at critical density across the whole run
    total_breach_ticks: int = sum(zone_breach_ticks.values())
    critical_density_duration_minutes: int = (
        total_breach_ticks * _POLLING_INTERVAL_MINUTES
    )

    return {
        "top_bottlenecks": top_bottleneck_names,
        "critical_density_duration_minutes": critical_density_duration_minutes,
        "snapshot_count": len(snapshots),
    }
