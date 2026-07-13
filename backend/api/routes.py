"""VenueSync — API Routing Layer.

Provides endpoints for fetching the venue snapshot, running reasoning cycles with
debouncing, approving actions idempotently, and loading critical demo scenarios.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.adapters import get_adapter
from backend.adapters.base import DataSourceAdapter
from backend.preprocessor.core import preprocess_snapshot, process_historical_run
from backend.preprocessor.intervention import (
    InterventionStateManager,
    compute_gate_closure_targets,
    compute_rain_shift_targets,
)
from backend.reasoning.core import generate_actions, generate_debrief
from backend.schemas import VenueSnapshot
from backend.schemas.reasoning import (
    ActionRecommendation,
    DebriefRequest,
    ReasoningCycleOutput,
)
from shared.schemas.domain import HistoricalMetrics, Incident, Occupancy

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Global State & Cache
# ---------------------------------------------------------------------------

_active_adapter: DataSourceAdapter | None = None
_reason_lock = asyncio.Lock()
_intervention_manager: InterventionStateManager | None = None

# Debounce cache for LLM reasoning cycle
_last_reason_time: float = 0.0
_cached_reason_output: ReasoningCycleOutput | None = None

# Known recommendations from reasoning engine
_known_actions: Dict[str, ActionRecommendation] = {}

# Approved actions (for idempotency tracking)
_approved_actions: Dict[str, Dict[str, Any]] = {}


def get_active_adapter() -> DataSourceAdapter:
    """Retrieve or lazily initialize the active data source adapter."""
    global _active_adapter
    if _active_adapter is None:
        source = os.environ.get("DATA_SOURCE", "synthetic")
        logger.info(f"Initializing active data source adapter: {source}")
        _active_adapter = get_adapter(source)
    return _active_adapter


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------


class ApproveResponse(BaseModel):
    """Schema for the action approval endpoint response."""

    status: str
    action_id: str
    already_approved: bool
    message: str


class LoadScenarioResponse(BaseModel):
    """Schema for the load scenario endpoint response."""

    status: str
    message: str


class GateClosureRequest(BaseModel):
    gate_id: str


class GateClosureResponse(BaseModel):
    status: str
    closed_gate: str
    redirect_targets: list[str]
    message: str


class RainSimulationResponse(BaseModel):
    status: str
    covered_zones: list[str]
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/snapshot", response_model=VenueSnapshot)
async def get_snapshot() -> VenueSnapshot:
    """Fetch the current canonical VenueSnapshot from the active Data Adapter."""
    adapter = get_active_adapter()
    snapshot = await adapter.get_snapshot()

    global _intervention_manager
    if _intervention_manager is not None:
        now = time.time()
        if _intervention_manager.is_complete(now):
            # Once the transition is complete, we leave the manager active
            # so the target state persists, or we can clear it.
            # If we clear it, the synthetic adapter might snap back to its
            # original simulation curve unless we updated its baseline.
            # For this demo, we keep the manager active indefinitely after completion
            # so the final blended state (alpha=1.0) persists.
            blended = _intervention_manager.get_blended_occupancies(now)
        else:
            blended = _intervention_manager.get_blended_occupancies(now)

        new_occupancies = []
        for occ in snapshot.occupancies:
            if occ.zone_id in blended:
                new_occ = Occupancy(
                    zone_id=occ.zone_id,
                    count=blended[occ.zone_id],
                    capacity=occ.capacity,
                    pct_capacity=occ.pct_capacity,
                    trend=occ.trend,
                )
                new_occupancies.append(new_occ)
            else:
                new_occupancies.append(occ)

        snapshot = VenueSnapshot(
            timestamp=snapshot.timestamp,
            zones=snapshot.zones,
            occupancies=new_occupancies,
            incidents=snapshot.incidents,
            staff=snapshot.staff,
        )

    return snapshot


@router.post("/reason", response_model=ReasoningCycleOutput)
async def run_reason() -> ReasoningCycleOutput:
    """Trigger the Reasoning Engine with a 15-second debounce mechanism.

    If a request is received within 15 seconds of the last execution, the cached
    ReasoningCycleOutput is returned instead of calling the LLM again.
    """
    global _last_reason_time, _cached_reason_output

    async with _reason_lock:
        current_time = time.time()
        if (
            _cached_reason_output is not None
            and (current_time - _last_reason_time) < 15.0
        ):
            logger.info("Returning cached reasoning output (debounced)")
            return _cached_reason_output

        logger.info("Triggering new LLM reasoning cycle")
        adapter = get_active_adapter()
        snapshot = await adapter.get_snapshot()
        processed_state = preprocess_snapshot(snapshot)

        # Generate actions (handles LLM calls, retries, fallbacks)
        output = generate_actions(processed_state)

        # Store generated recommendations in the known actions registry
        for action in output.actions:
            _known_actions[action.id] = action

        # Update debounce cache
        _last_reason_time = current_time
        _cached_reason_output = output

        return output


@router.post("/actions/{action_id}/approve", response_model=ApproveResponse)
async def approve_action(action_id: str) -> ApproveResponse:
    """Approve a recommended action by ID.

    Ensures that if the same action ID is approved multiple times (e.g., due to a
    double-click), the underlying state mutation is only executed once.
    """
    # Check if this action has already been approved
    if action_id in _approved_actions:
        logger.info(
            f"Action approval request for {action_id} ignored (already approved)"
        )
        return ApproveResponse(
            status="success",
            action_id=action_id,
            already_approved=True,
            message="Action was already approved (idempotent)",
        )

    # Verify that the action ID exists in the registry of known actions
    if action_id not in _known_actions:
        raise HTTPException(
            status_code=404,
            detail=f"Action ID '{action_id}' not found. It may have expired or was never generated.",
        )

    # Perform the underlying state mutation (simulated via logging and recording approval state)
    logger.info(f"Executing state mutation for action {action_id}")
    action_info = _known_actions[action_id]

    global _intervention_manager
    if _intervention_manager is None:
        adapter = get_active_adapter()
        snapshot = await adapter.get_snapshot()
        zones = await adapter.get_venue_graph()
        source_occs = {o.zone_id: o.count for o in snapshot.occupancies}

        # Determine targets based on action context
        # If action target zones contains a gate, simulate gate closure
        gate_targets = [z for z in action_info.target_zones if "gate" in z]
        if "close" in action_info.action_type.lower() and gate_targets:
            target_occs = compute_gate_closure_targets(
                zones, snapshot.occupancies, gate_targets[0]
            )
        else:
            # Fallback to generic weather/rain shift for any general redirect
            target_occs = compute_rain_shift_targets(zones, snapshot.occupancies)

        _intervention_manager = InterventionStateManager(
            approved_at=time.time(),
            source_occupancies=source_occs,
            target_occupancies=target_occs,
            duration=12.0,
        )

    _approved_actions[action_id] = {
        "timestamp": time.time(),
        "action": action_info,
    }

    return ApproveResponse(
        status="success",
        action_id=action_id,
        already_approved=False,
        message="Action approved and state mutation executed successfully",
    )


@router.get("/demo/load-scenario", response_model=LoadScenarioResponse)
async def load_scenario() -> LoadScenarioResponse:
    """Force the active data source adapter to override its state with a critical scenario.

    Loads a tense event state:
    - Zone 'gate_north' is at 98% capacity.
    - Active critical medical incident reported at 'gate_north'.
    """
    adapter = get_active_adapter()

    # Retrieve current topology and roster from active adapter to keep everything realistic
    zones = await adapter.get_venue_graph()
    staff = await adapter.get_staff_roster()

    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)

    occupancies = []
    for z in zones:
        if z.id == "gate_north":
            # Override gate_north to 98% capacity
            count = int(z.capacity * 0.98)
        else:
            # Other zones are set to a moderate 40% capacity
            count = int(z.capacity * 0.40)

        occupancies.append(
            Occupancy(
                zone_id=z.id,
                count=count,
                capacity=z.capacity,
                pct_capacity=0.0,
                trend="stable",
            )
        )

    incidents = [
        Incident(
            id="inc_demo_medical_001",
            zone_id="gate_north",
            type="medical",
            severity="critical",
            reported_at=now,
        )
    ]

    snapshot = VenueSnapshot(
        timestamp=now,
        zones=zones,
        occupancies=occupancies,
        incidents=incidents,
        staff=staff,
    )

    # Force the adapter to override its snapshot state
    adapter.set_override_snapshot(snapshot)

    # Clear reasoning cache and any active intervention
    global _cached_reason_output, _intervention_manager
    _cached_reason_output = None
    _intervention_manager = None

    logger.info("Loaded tense demo scenario (gate_north critical medical incident)")

    return LoadScenarioResponse(
        status="success",
        message="Tense demo scenario loaded successfully. 'gate_north' is at 98% capacity with an active medical incident.",
    )


@router.post("/demo/gate-closure", response_model=GateClosureResponse)
async def simulate_gate_closure(body: GateClosureRequest) -> GateClosureResponse:
    """Simulate closing a gate and redirecting crowd to alternatives.

    This acts as a scenario override and sets up a progressive crowd
    balancing intervention over a 12-second window.
    """
    global _intervention_manager, _cached_reason_output
    adapter = get_active_adapter()
    snapshot = await adapter.get_snapshot()
    zones = await adapter.get_venue_graph()

    source_occs = {o.zone_id: o.count for o in snapshot.occupancies}
    target_occs = compute_gate_closure_targets(
        zones, snapshot.occupancies, body.gate_id
    )

    _intervention_manager = InterventionStateManager(
        approved_at=time.time(),
        source_occupancies=source_occs,
        target_occupancies=target_occs,
        duration=12.0,
    )

    # Add an incident to reflect the reality
    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)
    new_incident = Incident(
        id=f"inc_gate_closure_{int(now.timestamp())}",
        zone_id=body.gate_id,
        type="security",
        severity="high",
        reported_at=now,
    )

    # We must patch the active adapter if it supports overrides,
    # but the simplest is just clearing reason cache so the next cycle sees the blended state.
    _cached_reason_output = None

    return GateClosureResponse(
        status="success",
        closed_gate=body.gate_id,
        redirect_targets=[
            z for z, c in target_occs.items() if c > source_occs.get(z, 0)
        ],
        message=f"Gate {body.gate_id} closed. Crowd redistributing over 12 seconds.",
    )


@router.post("/demo/rain-simulation", response_model=RainSimulationResponse)
async def simulate_rain() -> RainSimulationResponse:
    """Simulate sudden rain, causing crowd to seek covered zones.

    This sets up a progressive crowd balancing intervention over a 12-second window.
    """
    global _intervention_manager, _cached_reason_output
    adapter = get_active_adapter()
    snapshot = await adapter.get_snapshot()
    zones = await adapter.get_venue_graph()

    source_occs = {o.zone_id: o.count for o in snapshot.occupancies}
    target_occs = compute_rain_shift_targets(zones, snapshot.occupancies)

    _intervention_manager = InterventionStateManager(
        approved_at=time.time(),
        source_occupancies=source_occs,
        target_occupancies=target_occs,
        duration=12.0,
    )

    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)

    _cached_reason_output = None

    covered_zones = [z.id for z in zones if z.is_covered]

    return RainSimulationResponse(
        status="success",
        covered_zones=covered_zones,
        message="Rain simulation started. Crowd moving to covered zones over 12 seconds.",
    )


@router.post("/analytics/debrief", response_model=HistoricalMetrics)
async def run_debrief(body: DebriefRequest) -> HistoricalMetrics:
    """Aggregate a completed event run sequence into an Executive Summary payload.

    Pipeline (three-layer separation is strictly enforced):

    1. **Validation** — Pydantic rejects any malformed ``DebriefRequest`` body
       automatically before this handler is reached (HTTP 422).
    2. **Deterministic pre-processing** (Rule C) — ``process_historical_run()``
       computes all numeric metrics (breach counts, duration, bottleneck ranking)
       from the raw snapshot list.  No LLM is involved at this stage.
    3. **LLM reasoning** (Rule B) — ``generate_debrief()`` receives *only* the
       compressed metrics dict, never the raw snapshots (Rule A).  It produces a
       ``HistoricalMetrics`` object with a structured ``executive_summary`` field.
    4. **Output validation** — the result is validated against ``HistoricalMetrics``
       before being returned.  On ``ValidationError`` the endpoint drops to an inert
       fallback instead of propagating a 500.

    Args:
        body: Validated ``DebriefRequest`` containing the ordered snapshot list.

    Returns:
        A ``HistoricalMetrics`` response with top bottlenecks, total critical-density
        duration, and an LLM-generated executive summary.

    Raises:
        HTTPException 422: If ``body.snapshots`` is empty.
        HTTPException 500: On unexpected non-validation errors.
    """
    # Guard: empty snapshot list is a client error, not a server error
    if not body.snapshots:
        raise HTTPException(
            status_code=422,
            detail="'snapshots' must contain at least one VenueSnapshot.",
        )

    try:
        # --- Step 1: Deterministic aggregation (Rule C) ---
        # All arithmetic lives here — the LLM never touches these numbers.
        compressed_metrics: dict = process_historical_run(body.snapshots)

        logger.info(
            "Debrief pre-processing complete: %d snapshots, %d critical zone-minutes, "
            "top bottlenecks: %s",
            compressed_metrics["snapshot_count"],
            compressed_metrics["critical_density_duration_minutes"],
            compressed_metrics["top_bottlenecks"],
        )

        # --- Step 2: LLM reasoning for executive summary (Rule B) ---
        # generate_debrief() handles its own retry + fallback internally.
        # Raw snapshots are NOT passed — only the compressed metrics dict (Rule A).
        result: HistoricalMetrics = generate_debrief(compressed_metrics)

        # --- Step 3: Final schema validation gate (Rule B) ---
        # Validates the object returned by generate_debrief before it leaves
        # this handler, catching any edge-case schema drift.
        validated: HistoricalMetrics = HistoricalMetrics.model_validate(
            result.model_dump()
        )
        return validated

    except Exception as exc:
        # Catch-all for unexpected failures (e.g. adapter errors, import issues).
        # ValidationError from the final gate above is also caught here and returns
        # the inert fallback instead of a 500.
        from pydantic import ValidationError as PydanticValidationError

        if isinstance(exc, PydanticValidationError):
            logger.warning(
                "Final HistoricalMetrics validation failed — returning inert fallback. "
                "Error: %s",
                exc,
            )
            return HistoricalMetrics(
                top_bottlenecks=compressed_metrics.get("top_bottlenecks") or ["unknown"],  # type: ignore[possibly-undefined]
                critical_density_duration_minutes=compressed_metrics.get(  # type: ignore[possibly-undefined]
                    "critical_density_duration_minutes", 0
                ),
                executive_summary=(
                    "System running in degraded mode — debrief validation failed. "
                    "Manual review of the run data is required."
                ),
            )

        logger.exception("Unexpected error in /analytics/debrief: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while generating the debrief summary.",
        ) from exc
