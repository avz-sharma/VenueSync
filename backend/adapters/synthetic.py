"""VenueSync — Synthetic Data Adapter.

Generates realistic venue data for development and testing.
Simulates arrival waves, halftime surges, egress patterns, and
randomized incidents across a configurable event timeline.

Timezone : UTC — tournament-grade time tracking.
Clock    : Advances by ``tick_minutes`` per ``get_snapshot()`` call.
Seed     : Deterministic RNG for reproducible test runs.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from backend.adapters.base import DataSourceAdapter
from shared.schemas.domain import (
    Incident,
    Occupancy,
    Staff,
    VenueSnapshot,
    Zone,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TIMEZONE = timezone.utc
_DEFAULT_TICK_MINUTES: int = 5

# Event phases (minutes relative to event start, T=0)
_ARRIVAL_START: int = -60  # Gates open 1 hour before kickoff
_FIRST_HALF_END: int = 45
_HALFTIME_END: int = 60
_SECOND_HALF_END: int = 105
_EGRESS_END: int = 135

_INCIDENT_TYPES: list[str] = [
    "medical",
    "security",
    "overcrowding",
    "equipment_failure",
    "weather",
]

# ---------------------------------------------------------------------------
# Venue definition — 8-zone stadium graph
# ---------------------------------------------------------------------------

from typing import TypedDict, List, Literal


class ZoneTemplate(TypedDict, total=False):
    id: str
    name: str
    capacity: int
    adjacent_zones: List[str]
    is_covered: bool


class StaffTemplate(TypedDict):
    id: str
    role: Literal["security", "medical", "operations", "hospitality"]
    zone_id: str


_VENUE_ZONES: list[ZoneTemplate] = [
    {
        "id": "gate_north",
        "name": "North Gate",
        "capacity": 2000,
        "adjacent_zones": ["concourse_a"],
        "is_covered": False,
    },
    {
        "id": "gate_south",
        "name": "South Gate",
        "capacity": 2000,
        "adjacent_zones": ["concourse_b"],
        "is_covered": False,
    },
    {
        "id": "concourse_a",
        "name": "Concourse A",
        "capacity": 3000,
        "is_covered": True,
        "adjacent_zones": [
            "gate_north",
            "stand_east",
            "vip_lounge",
            "food_court",
        ],
    },
    {
        "id": "concourse_b",
        "name": "Concourse B",
        "capacity": 3000,
        "is_covered": True,
        "adjacent_zones": [
            "gate_south",
            "stand_west",
            "vip_lounge",
            "food_court",
        ],
    },
    {
        "id": "stand_east",
        "name": "East Stand",
        "capacity": 5000,
        "adjacent_zones": ["concourse_a"],
        "is_covered": False,
    },
    {
        "id": "stand_west",
        "name": "West Stand",
        "capacity": 5000,
        "adjacent_zones": ["concourse_b"],
        "is_covered": False,
    },
    {
        "id": "vip_lounge",
        "name": "VIP Lounge",
        "capacity": 500,
        "is_covered": True,
        "adjacent_zones": ["concourse_a", "concourse_b"],
    },
    {
        "id": "food_court",
        "name": "Food Court",
        "capacity": 1500,
        "adjacent_zones": ["concourse_a", "concourse_b"],
        "is_covered": False,
    },
]

# ---------------------------------------------------------------------------
# Occupancy keyframe curves — (elapsed_minutes, occupancy_factor)
#
# Each zone type follows a distinct pattern across the event lifecycle.
# Values are linearly interpolated between keyframes.
# ---------------------------------------------------------------------------

_ZONE_CURVES: dict[str, list[tuple[int, float]]] = {
    # Gates: peak during arrival & egress, near-empty during play
    "gate": [
        (_ARRIVAL_START, 0.00),
        (-30, 0.70),
        (-10, 0.50),
        (0, 0.15),
        (_FIRST_HALF_END, 0.05),
        (_HALFTIME_END, 0.05),
        (_SECOND_HALF_END, 0.10),
        (115, 0.80),
        (_EGRESS_END, 0.10),
    ],
    # Stands: fill during arrival, near capacity during play, halftime dip
    "stand": [
        (_ARRIVAL_START, 0.00),
        (-30, 0.20),
        (-10, 0.55),
        (0, 0.75),
        (20, 0.85),
        (_FIRST_HALF_END, 0.88),
        (52, 0.55),
        (_HALFTIME_END, 0.60),
        (80, 0.82),
        (_SECOND_HALF_END, 0.80),
        (115, 0.40),
        (_EGRESS_END, 0.05),
    ],
    # Concourses: transit zones, busiest at transitions
    "concourse": [
        (_ARRIVAL_START, 0.00),
        (-30, 0.45),
        (-10, 0.55),
        (0, 0.30),
        (_FIRST_HALF_END, 0.20),
        (50, 0.65),
        (_HALFTIME_END, 0.50),
        (_SECOND_HALF_END, 0.25),
        (110, 0.55),
        (_EGRESS_END, 0.10),
    ],
    # Food court: peaks at halftime
    "food_court": [
        (_ARRIVAL_START, 0.00),
        (-30, 0.10),
        (0, 0.15),
        (20, 0.20),
        (_FIRST_HALF_END, 0.30),
        (50, 0.85),
        (55, 0.90),
        (_HALFTIME_END, 0.70),
        (80, 0.25),
        (_SECOND_HALF_END, 0.15),
        (115, 0.10),
        (_EGRESS_END, 0.05),
    ],
    # VIP lounge: steady moderate occupancy
    "vip_lounge": [
        (_ARRIVAL_START, 0.00),
        (-30, 0.25),
        (0, 0.50),
        (_FIRST_HALF_END, 0.60),
        (50, 0.70),
        (_HALFTIME_END, 0.65),
        (_SECOND_HALF_END, 0.55),
        (115, 0.30),
        (_EGRESS_END, 0.05),
    ],
}

# ---------------------------------------------------------------------------
# Staff roster template
# ---------------------------------------------------------------------------

_STAFF_TEMPLATE: list[StaffTemplate] = [
    # Security (7)
    {"id": "staff_sec_01", "role": "security", "zone_id": "gate_north"},
    {"id": "staff_sec_02", "role": "security", "zone_id": "gate_south"},
    {"id": "staff_sec_03", "role": "security", "zone_id": "stand_east"},
    {"id": "staff_sec_04", "role": "security", "zone_id": "stand_west"},
    {"id": "staff_sec_05", "role": "security", "zone_id": "concourse_a"},
    {"id": "staff_sec_06", "role": "security", "zone_id": "concourse_b"},
    {"id": "staff_sec_07", "role": "security", "zone_id": "vip_lounge"},
    # Medical (3)
    {"id": "staff_med_01", "role": "medical", "zone_id": "stand_east"},
    {"id": "staff_med_02", "role": "medical", "zone_id": "stand_west"},
    {"id": "staff_med_03", "role": "medical", "zone_id": "concourse_a"},
    # Operations (4)
    {"id": "staff_ops_01", "role": "operations", "zone_id": "gate_north"},
    {"id": "staff_ops_02", "role": "operations", "zone_id": "gate_south"},
    {"id": "staff_ops_03", "role": "operations", "zone_id": "food_court"},
    {"id": "staff_ops_04", "role": "operations", "zone_id": "concourse_b"},
    # Hospitality (3)
    {"id": "staff_hos_01", "role": "hospitality", "zone_id": "vip_lounge"},
    {"id": "staff_hos_02", "role": "hospitality", "zone_id": "food_court"},
    {"id": "staff_hos_03", "role": "hospitality", "zone_id": "food_court"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_zone_curve_key(zone_id: str) -> str:
    """Map a zone ID to its occupancy curve key."""
    if zone_id.startswith("gate_"):
        return "gate"
    if zone_id.startswith("stand_"):
        return "stand"
    if zone_id.startswith("concourse_"):
        return "concourse"
    # Exact-match zones
    if zone_id in _ZONE_CURVES:
        return zone_id
    return "concourse"  # fallback


def _interpolate(keyframes: list[tuple[int, float]], t: int) -> float:
    """Linearly interpolate between occupancy keyframes."""
    if t <= keyframes[0][0]:
        return keyframes[0][1]
    if t >= keyframes[-1][0]:
        return keyframes[-1][1]

    for i in range(len(keyframes) - 1):
        t0, v0 = keyframes[i]
        t1, v1 = keyframes[i + 1]
        if t0 <= t <= t1:
            progress: float = (t - t0) / (t1 - t0) if t1 != t0 else 0.0
            return v0 + (v1 - v0) * progress

    return keyframes[-1][1]


# ---------------------------------------------------------------------------
# SyntheticAdapter
# ---------------------------------------------------------------------------


class SyntheticAdapter(DataSourceAdapter):
    """Generates realistic synthetic venue data.

    Simulates a live event with:
    - Arrival waves through gates → concourses → stands
    - Halftime food court surges
    - Post-event egress draining through gates
    - Randomized incidents scaled by occupancy density
    - Staff status cycling based on incident state

    Each call to ``get_snapshot()`` advances the simulation clock by
    ``tick_minutes``.  All timestamps use UTC.
    """

    def __init__(
        self,
        seed: int = 42,
        tick_minutes: int = _DEFAULT_TICK_MINUTES,
    ) -> None:
        self._tick: int = 0
        self._tick_minutes: int = tick_minutes
        self._rng: random.Random = random.Random(seed)
        self._zones: list[Zone] = [Zone(**z) for z in _VENUE_ZONES]
        self._zone_map: dict[str, Zone] = {z.id: z for z in self._zones}
        self._previous_counts: dict[str, int] = {z.id: 0 for z in self._zones}

        # Event starts at 18:00 IST today
        now: datetime = datetime.now(_TIMEZONE)
        self._event_start: datetime = now.replace(
            hour=18, minute=0, second=0, microsecond=0
        )
        self._override_snapshot: VenueSnapshot | None = None

    def set_override_snapshot(self, snapshot: VenueSnapshot | None) -> None:
        """Override the adapter's snapshot state (used for demo scenarios)."""
        self._override_snapshot = snapshot

    # -------------------------------------------------------------------
    # Public interface (DataSourceAdapter)
    # -------------------------------------------------------------------

    async def get_snapshot(self) -> VenueSnapshot:
        """Generate the next simulation tick's venue state."""
        if self._override_snapshot is not None:
            return self._override_snapshot

        elapsed: int = self._tick * self._tick_minutes + _ARRIVAL_START
        current_time: datetime = self._event_start + timedelta(minutes=elapsed)

        occupancies: list[Occupancy] = self._generate_occupancies(elapsed)
        incidents: list[Incident] = self._generate_incidents(
            elapsed, current_time, occupancies
        )
        staff: list[Staff] = self._generate_staff(incidents)

        snapshot = VenueSnapshot(
            timestamp=current_time,
            zones=self._zones,
            occupancies=occupancies,
            incidents=incidents,
            staff=staff,
        )

        # Advance simulation state
        self._previous_counts = {occ.zone_id: occ.count for occ in occupancies}
        self._tick += 1

        return snapshot

    async def get_venue_graph(self) -> list[Zone]:
        """Return the static venue zone topology."""
        return list(self._zones)

    async def get_staff_roster(self) -> list[Staff]:
        """Return the baseline staff roster (all on_duty)."""
        return [
            Staff(
                id=s["id"],
                role=s["role"],
                zone_id=s["zone_id"],
                status="on_duty",
            )
            for s in _STAFF_TEMPLATE
        ]

    # -------------------------------------------------------------------
    # Occupancy generation
    # -------------------------------------------------------------------

    def _generate_occupancies(self, elapsed: int) -> list[Occupancy]:
        """Compute occupancy for every zone using keyframe interpolation + noise."""
        occupancies: list[Occupancy] = []

        for zone in self._zones:
            curve_key: str = _get_zone_curve_key(zone.id)
            keyframes: list[tuple[int, float]] = _ZONE_CURVES[curve_key]
            base_factor: float = _interpolate(keyframes, elapsed)

            # Gaussian noise (σ = 5% of capacity) for realism
            noise: float = self._rng.gauss(0.0, 0.05)
            factor: float = max(0.0, min(1.0, base_factor + noise))
            count: int = int(zone.capacity * factor)

            # Compute trend from previous tick
            prev: int = self._previous_counts.get(zone.id, 0)
            delta: int = count - prev
            threshold: int = max(1, int(zone.capacity * 0.02))
            if delta > threshold:
                trend = "rising"
            elif delta < -threshold:
                trend = "falling"
            else:
                trend = "stable"

            occupancies.append(
                Occupancy(
                    zone_id=zone.id,
                    count=count,
                    capacity=zone.capacity,
                    trend=trend,
                )
            )

        return occupancies

    # -------------------------------------------------------------------
    # Incident generation
    # -------------------------------------------------------------------

    def _generate_incidents(
        self,
        elapsed: int,
        current_time: datetime,
        occupancies: list[Occupancy],
    ) -> list[Incident]:
        """Generate random incidents scaled by occupancy density.

        Higher occupancy → higher incident probability and severity.
        No incidents generated before gates open or after egress completes.
        """
        if elapsed < _ARRIVAL_START or elapsed > _EGRESS_END:
            return []

        incidents: list[Incident] = []

        for occ in occupancies:
            density: float = occ.count / occ.capacity if occ.capacity > 0 else 0.0
            # 3% base probability, up to ~15% at full capacity
            incident_prob: float = 0.03 + 0.12 * density

            if self._rng.random() < incident_prob:
                incident_type: str = self._rng.choice(_INCIDENT_TYPES)
                severity: str = self._weighted_severity(density)

                # Incident reported sometime within the current tick window
                offset_seconds: int = self._rng.randint(0, self._tick_minutes * 60)
                reported_at: datetime = current_time - timedelta(seconds=offset_seconds)

                incidents.append(
                    Incident(
                        id=f"inc_{self._rng.getrandbits(32):08x}",
                        zone_id=occ.zone_id,
                        type=incident_type,
                        severity=severity,
                        reported_at=reported_at,
                    )
                )

        return incidents

    def _weighted_severity(self, density: float) -> str:
        """Select incident severity weighted by occupancy density.

        Higher density shifts probability toward more severe incidents.
        """
        weights: list[float] = [
            max(0.10, 0.45 - 0.30 * density),  # low
            0.30,  # medium
            min(0.35, 0.18 + 0.15 * density),  # high
            min(0.15, 0.07 + 0.08 * density),  # critical
        ]
        return self._rng.choices(
            ["low", "medium", "high", "critical"],
            weights=weights,
            k=1,
        )[0]

    # -------------------------------------------------------------------
    # Staff generation
    # -------------------------------------------------------------------

    def _generate_staff(self, incidents: list[Incident]) -> list[Staff]:
        """Generate staff statuses influenced by active incidents.

        Security and medical staff in zones with incidents have elevated
        probability of 'responding' status.
        """
        incident_zones: frozenset[str] = frozenset(inc.zone_id for inc in incidents)

        staff_list: list[Staff] = []
        for template in _STAFF_TEMPLATE:
            zone_id: str = template["zone_id"]
            role: str = template["role"]

            if zone_id in incident_zones and role in ("security", "medical"):
                status: str = self._rng.choice(["responding", "on_duty"])
            elif self._rng.random() < 0.05:
                status = "break"
            else:
                status = "on_duty"

            staff_list.append(
                Staff(
                    id=template["id"],
                    role=role,
                    zone_id=zone_id,
                    status=status,
                )
            )

        return staff_list
