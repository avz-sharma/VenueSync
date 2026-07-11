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
