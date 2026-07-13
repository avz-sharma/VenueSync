"""VenueSync — Preprocessor Intervention Logic.

Implements Rule C deterministic math for overriding venue states and
progressively balancing crowd densities. No LLM reasoning happens here.
"""

from __future__ import annotations

from typing import Dict, List

from shared.schemas.domain import Occupancy, Zone


def compute_alpha(approved_at: float, now: float, duration: float) -> float:
    """Compute the linear interpolation factor alpha [0.0, 1.0]."""
    if duration <= 0:
        return 1.0
    elapsed = now - approved_at
    alpha = elapsed / duration
    return max(0.0, min(1.0, alpha))


def blend_occupancy(source: int, target: int, alpha: float) -> int:
    """Linearly interpolate occupancy between source and target counts."""
    return round(source + (target - source) * alpha)


def compute_gate_closure_targets(
    zones: List[Zone], occupancies: List[Occupancy], closed_gate_id: str
) -> Dict[str, int]:
    """Compute target occupancies when a gate is closed.

    The closed gate's occupancy is reduced to 0.
    The evacuated crowd is redistributed to the alternate gate ('gate_south')
    and any adjacent concourses.
    Total headcount is conserved.
    """
    source_occs = {o.zone_id: o.count for o in occupancies}
    target_occs = source_occs.copy()

    closed_count = target_occs.get(closed_gate_id, 0)
    if closed_count == 0:
        return target_occs

    target_occs[closed_gate_id] = 0

    # Identify target zones: gate_south + concourses
    redirect_targets = []
    for z in zones:
        if z.id == "gate_south" and closed_gate_id != "gate_south":
            redirect_targets.append(z.id)
        elif z.id.startswith("concourse_"):
            redirect_targets.append(z.id)

    if not redirect_targets:
        return target_occs

    # Evenly distribute the crowd
    split = closed_count // len(redirect_targets)
    remainder = closed_count % len(redirect_targets)

    for idx, t_id in enumerate(redirect_targets):
        target_occs[t_id] = target_occs.get(t_id, 0) + split
        if idx < remainder:
            target_occs[t_id] += 1

    return target_occs


def compute_rain_shift_targets(
    zones: List[Zone], occupancies: List[Occupancy]
) -> Dict[str, int]:
    """Compute target occupancies for a rain simulation.

    Crowd in exposed zones shifts to covered zones, proportionally to
    the remaining capacity in those covered zones.
    Total headcount is conserved.
    """
    source_occs = {o.zone_id: o.count for o in occupancies}
    target_occs = source_occs.copy()

    covered_ids = {z.id for z in zones if z.is_covered}
    exposed_ids = {z.id for z in zones if not z.is_covered}

    if not covered_ids or not exposed_ids:
        return target_occs

    total_exposed_moving = 0
    for e_id in exposed_ids:
        # Move 50% of the crowd from exposed zones to covered zones
        moving = int(target_occs.get(e_id, 0) * 0.5)
        target_occs[e_id] -= moving
        total_exposed_moving += moving

    if total_exposed_moving == 0:
        return target_occs

    # Compute total remaining capacity in covered zones
    zone_capacities = {z.id: z.capacity for z in zones}
    covered_remaining = {}
    for c_id in covered_ids:
        cap = zone_capacities.get(c_id, 0)
        curr = target_occs.get(c_id, 0)
        covered_remaining[c_id] = max(0, cap - curr)

    total_remaining_capacity = sum(covered_remaining.values())

    if total_remaining_capacity == 0:
        # Just split evenly if they're all full
        split = total_exposed_moving // len(covered_ids)
        rem = total_exposed_moving % len(covered_ids)
        for idx, c_id in enumerate(covered_ids):
            target_occs[c_id] = (
                target_occs.get(c_id, 0) + split + (1 if idx < rem else 0)
            )
    else:
        # Distribute proportionally based on remaining capacity
        distributed = 0
        sorted_covered = sorted(
            covered_remaining.items(), key=lambda x: x[1], reverse=True
        )

        for idx, (c_id, rem_cap) in enumerate(sorted_covered):
            if idx == len(sorted_covered) - 1:
                # Give all remaining to the last one to avoid rounding losses
                to_add = total_exposed_moving - distributed
            else:
                to_add = int(
                    total_exposed_moving * (rem_cap / total_remaining_capacity)
                )

            target_occs[c_id] = target_occs.get(c_id, 0) + to_add
            distributed += to_add

    return target_occs


class InterventionStateManager:
    """Tracks the state of a progressive crowd balancing intervention."""

    def __init__(
        self,
        approved_at: float,
        source_occupancies: Dict[str, int],
        target_occupancies: Dict[str, int],
        duration: float = 12.0,
    ):
        self.approved_at = approved_at
        self.source_occupancies = source_occupancies
        self.target_occupancies = target_occupancies
        self.duration = duration

    def get_blended_occupancies(self, now: float) -> Dict[str, int]:
        """Compute the interpolated occupancies for the current time."""
        alpha = compute_alpha(self.approved_at, now, self.duration)
        blended = {}
        for zone_id, source_count in self.source_occupancies.items():
            target_count = self.target_occupancies.get(zone_id, source_count)
            blended[zone_id] = blend_occupancy(source_count, target_count, alpha)
        return blended

    def is_complete(self, now: float) -> bool:
        """Check if the intervention transition has finished."""
        return (now - self.approved_at) >= self.duration
