"""VenueSync — API Routing Layer.

Provides endpoints for fetching the venue snapshot, running reasoning cycles with
debouncing, approving actions idempotently, and loading critical demo scenarios.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.adapters import get_adapter
from backend.adapters.base import DataSourceAdapter
from backend.preprocessor.core import (
    preprocess_snapshot,
    process_historical_run,
    compute_pre_alert_zones,
)
from backend.preprocessor.intervention import (
    InterventionStateManager,
    compute_gate_closure_targets,
    compute_rain_shift_targets,
)
from backend.reasoning.core import generate_actions, generate_debrief
from backend.reasoning.pre_alert import generate_pre_alert
from backend.reasoning.operator_qa import generate_operator_response
from backend.reasoning.scenario_planner import generate_scenario
from backend.schemas import VenueSnapshot
from backend.schemas.reasoning import (
    ActionRecommendation,
    DebriefRequest,
    GenerateScenarioRequest,
    OperatorQueryRequest,
    OperatorQueryResponse,
    PreAlertOutput,
    ReasoningCycleOutput,
    ScenarioSpec,
)
from shared.schemas.domain import HistoricalMetrics, Incident, Occupancy
from backend.api.state import VenueSyncState, get_app_state

logger = logging.getLogger(__name__)

router = APIRouter()


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
async def get_snapshot(state: VenueSyncState = Depends(get_app_state)) -> VenueSnapshot:
    """Fetch the current canonical VenueSnapshot from the active Data Adapter."""
    adapter = state.get_adapter()
    snapshot = await adapter.get_snapshot()

    if state.intervention_manager is not None:
        now = time.time()
        blended = state.intervention_manager.get_blended_occupancies(now)

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
async def run_reason(
    state: VenueSyncState = Depends(get_app_state),
) -> ReasoningCycleOutput:
    """Trigger the Reasoning Engine with a 15-second debounce mechanism.

    If a request is received within 15 seconds of the last execution, the cached
    ReasoningCycleOutput is returned instead of calling the LLM again.
    """
    async with state.reason_lock:
        state.prune_expired_actions()
        current_time = time.time()
        if (
            state.cached_reason_output is not None
            and (current_time - state.last_reason_time) < 15.0
        ):
            logger.info("Returning cached reasoning output (debounced)")
            return state.cached_reason_output

        logger.info("Triggering new LLM reasoning cycle")
        adapter = state.get_adapter()
        snapshot = await adapter.get_snapshot()
        processed_state = preprocess_snapshot(snapshot)

        # Generate actions via asyncio.to_thread to avoid blocking the event loop
        output = await asyncio.to_thread(generate_actions, processed_state)

        # Store generated recommendations in the known actions registry
        for action in output.actions:
            state.known_actions[action.id] = action

        # Update debounce cache
        state.last_reason_time = current_time
        state.cached_reason_output = output

        return output


@router.post("/actions/{action_id}/approve", response_model=ApproveResponse)
async def approve_action(
    action_id: str, state: VenueSyncState = Depends(get_app_state)
) -> ApproveResponse:
    """Approve a recommended action by ID.

    Ensures that if the same action ID is approved multiple times (e.g., due to a
    double-click), the underlying state mutation is only executed once.

    Every newly approved action instantiates a fresh InterventionStateManager,
    completely replacing the old one. The entire state mutation is wrapped in
    the reason lock to prevent concurrent API calls from clobbering state.
    """
    async with state.reason_lock:
        # Check if this action has already been approved
        if action_id in state.approved_actions:
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
        if action_id not in state.known_actions:
            raise HTTPException(
                status_code=404,
                detail=f"Action ID '{action_id}' not found. It may have expired or was never generated.",
            )

        # Perform the underlying state mutation
        logger.info(f"Executing state mutation for action {action_id}")
        action_info = state.known_actions[action_id]

        adapter = state.get_adapter()
        snapshot = await adapter.get_snapshot()
        zones = await adapter.get_venue_graph()
        source_occs = {o.zone_id: o.count for o in snapshot.occupancies}

        # Route action type to the correct intervention computation
        if action_info.action_type == "open_emergency_exit":
            # Gate closure: redirect from the first target zone (the gate)
            gate_targets = action_info.target_zones
            gate_id = gate_targets[0] if gate_targets else "gate_north"
            target_occs = compute_gate_closure_targets(
                zones, snapshot.occupancies, gate_id
            )
        elif action_info.action_type == "redirect_crowd":
            # Weather/general redirect: shift crowd to covered zones
            target_occs = compute_rain_shift_targets(zones, snapshot.occupancies)
        else:
            # dispatch_medical, dispatch_security, broadcast_announcement
            # These are dispatch/announcement actions — no stadium-wide crowd shift
            target_occs = source_occs.copy()

        # Always instantiate a fresh InterventionStateManager, replacing any old one
        state.intervention_manager = InterventionStateManager(
            approved_at=time.time(),
            source_occupancies=source_occs,
            target_occupancies=target_occs,
            duration=12.0,
        )

        state.approved_actions[action_id] = {
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
async def load_scenario(
    state: VenueSyncState = Depends(get_app_state),
) -> LoadScenarioResponse:
    """Force the active data source adapter to override its state with a critical scenario.

    Loads a tense event state:
    - Zone 'gate_north' is at 98% capacity.
    - Active critical medical incident reported at 'gate_north'.
    """
    adapter = state.get_adapter()

    # Retrieve current topology and roster from active adapter to keep everything realistic
    zones = await adapter.get_venue_graph()
    staff = await adapter.get_staff_roster()

    now = datetime.now(timezone.utc)

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
    state.cached_reason_output = None
    state.intervention_manager = None

    logger.info("Loaded tense demo scenario (gate_north critical medical incident)")

    return LoadScenarioResponse(
        status="success",
        message="Tense demo scenario loaded successfully. 'gate_north' is at 98% capacity with an active medical incident.",
    )


@router.post("/demo/gate-closure", response_model=GateClosureResponse)
async def simulate_gate_closure(
    body: GateClosureRequest, state: VenueSyncState = Depends(get_app_state)
) -> GateClosureResponse:
    """Simulate closing a gate and redirecting crowd to alternatives.

    This acts as a scenario override and sets up a progressive crowd
    balancing intervention over a 12-second window.
    """
    adapter = state.get_adapter()
    snapshot = await adapter.get_snapshot()
    zones = await adapter.get_venue_graph()

    source_occs = {o.zone_id: o.count for o in snapshot.occupancies}
    target_occs = compute_gate_closure_targets(
        zones, snapshot.occupancies, body.gate_id
    )

    state.intervention_manager = InterventionStateManager(
        approved_at=time.time(),
        source_occupancies=source_occs,
        target_occupancies=target_occs,
        duration=12.0,
    )

    # Add an incident to reflect the reality and wire it into the adapter
    now = datetime.now(timezone.utc)
    new_incident = Incident(
        id=f"inc_gate_closure_{int(now.timestamp())}",
        zone_id=body.gate_id,
        type="security",
        severity="high",
        reported_at=now,
    )

    # Build a patched snapshot with the new incident and updated occupancies
    patched_occupancies = []
    for occ in snapshot.occupancies:
        if occ.zone_id in target_occs:
            patched_occupancies.append(
                Occupancy(
                    zone_id=occ.zone_id,
                    count=target_occs[occ.zone_id],
                    capacity=occ.capacity,
                    pct_capacity=occ.pct_capacity,
                    trend=occ.trend,
                )
            )
        else:
            patched_occupancies.append(occ)

    patched_snapshot = VenueSnapshot(
        timestamp=now,
        zones=snapshot.zones,
        occupancies=patched_occupancies,
        incidents=list(snapshot.incidents) + [new_incident],
        staff=snapshot.staff,
    )
    adapter.set_override_snapshot(patched_snapshot)

    state.cached_reason_output = None

    return GateClosureResponse(
        status="success",
        closed_gate=body.gate_id,
        redirect_targets=[
            z for z, c in target_occs.items() if c > source_occs.get(z, 0)
        ],
        message=f"Gate {body.gate_id} closed. Crowd redistributing over 12 seconds.",
    )


@router.post("/demo/rain-simulation", response_model=RainSimulationResponse)
async def simulate_rain(
    state: VenueSyncState = Depends(get_app_state),
) -> RainSimulationResponse:
    """Simulate sudden rain, causing crowd to seek covered zones.

    This sets up a progressive crowd balancing intervention over a 12-second window.
    """
    adapter = state.get_adapter()
    snapshot = await adapter.get_snapshot()
    zones = await adapter.get_venue_graph()

    source_occs = {o.zone_id: o.count for o in snapshot.occupancies}
    target_occs = compute_rain_shift_targets(zones, snapshot.occupancies)

    state.intervention_manager = InterventionStateManager(
        approved_at=time.time(),
        source_occupancies=source_occs,
        target_occupancies=target_occs,
        duration=12.0,
    )

    now = datetime.now(timezone.utc)

    state.cached_reason_output = None

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
        # Wrapped in asyncio.to_thread to avoid blocking the event loop.
        result: HistoricalMetrics = await asyncio.to_thread(
            generate_debrief, compressed_metrics
        )

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
                top_bottlenecks=compressed_metrics.get("top_bottlenecks", ["unknown"]),
                critical_density_duration_minutes=compressed_metrics.get(
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


# ---------------------------------------------------------------------------
# Pre-Alert Engine endpoint (Component 1)
# ---------------------------------------------------------------------------


@router.get("/pre-alert", response_model=PreAlertOutput)
async def get_pre_alert(
    state: VenueSyncState = Depends(get_app_state),
) -> PreAlertOutput:
    """Return predictive risk assessment for zones approaching critical density.

    Pipeline:
    1. Fetch current snapshot from the active adapter.
    2. Deterministic trajectory scoring via ``compute_pre_alert_zones()`` (Rule C).
    3. If any zones qualify, pass preprocessed trajectory data to the Pre-Alert
       LLM reasoning engine (Rule A — no raw data).
    4. Validate output against ``PreAlertOutput`` schema (Rule B).
    """
    adapter = state.get_adapter()
    snapshot = await adapter.get_snapshot()

    # Step 1: Deterministic pre-processing (Rule C)
    pre_alert_zones = compute_pre_alert_zones(snapshot)

    if not pre_alert_zones:
        return PreAlertOutput(alerts=[], degraded_mode=False)

    # Step 2: LLM reasoning for preemptive recommendations (Rule B)
    output = await asyncio.to_thread(generate_pre_alert, pre_alert_zones)
    return output


# ---------------------------------------------------------------------------
# Operator Chat Q&A endpoint (Component 2)
# ---------------------------------------------------------------------------


@router.post("/operator/query", response_model=OperatorQueryResponse)
async def operator_query(
    body: OperatorQueryRequest, state: VenueSyncState = Depends(get_app_state)
) -> OperatorQueryResponse:
    """Answer a natural-language question from the venue operator.

    Pipeline:
    1. Fetch current snapshot and preprocess it (Rule A/C — LLM receives
       only preprocessed dict, never raw snapshot).
    2. Pass preprocessed state + sanitized query to the Operator Q&A engine.
    3. Validate output against ``OperatorQueryResponse`` schema (Rule B).

    Throttled with a 5-second debounce (separate from the 15s reasoning debounce).
    """
    current_time = time.time()
    if (
        state.cached_operator_response is not None
        and (current_time - state.last_operator_query_time) < 5.0
    ):
        logger.info("Returning cached operator response (5s throttled)")
        return state.cached_operator_response

    adapter = state.get_adapter()
    snapshot = await adapter.get_snapshot()
    processed_state = preprocess_snapshot(snapshot)

    # LLM call — operator query is treated as untrusted input (Rule D)
    output = await asyncio.to_thread(
        generate_operator_response, body.query, processed_state
    )

    state.last_operator_query_time = current_time
    state.cached_operator_response = output

    return output


# ---------------------------------------------------------------------------
# GenAI Scenario Generator endpoint (Component 3 — Advanced option)
# ---------------------------------------------------------------------------


class GenerateScenarioResponse(BaseModel):
    """Response for the GenAI scenario generator."""

    status: str
    scenario: ScenarioSpec
    message: str


@router.post("/demo/generate-scenario", response_model=GenerateScenarioResponse)
async def generate_scenario_endpoint(
    body: GenerateScenarioRequest, state: VenueSyncState = Depends(get_app_state)
) -> GenerateScenarioResponse:
    """Generate a novel event scenario from a natural-language description.

    Pipeline:
    1. Retrieve available zone IDs from the venue topology.
    2. Pass description + zone IDs to the GenAI Scenario Planner (Rule D —
       description is treated as untrusted input).
    3. Validate output against ``ScenarioSpec`` schema (Rule B).
    4. Translate scenario intents into deterministic occupancy mutations
       via the intervention engine (Rule C — GenAI never does arithmetic).

    This coexists with the hardcoded demo scenarios as an "Advanced" option.
    """
    adapter = state.get_adapter()
    snapshot = await adapter.get_snapshot()
    zones = await adapter.get_venue_graph()
    available_zone_ids = [z.id for z in zones]

    # Step 1: GenAI generates the scenario spec
    scenario_spec = await asyncio.to_thread(
        generate_scenario, body.description, available_zone_ids
    )

    # Step 2: Translate intents into deterministic occupancy mutations (Rule C)
    source_occs = {o.zone_id: o.count for o in snapshot.occupancies}
    target_occs = dict(source_occs)  # Start from current state
    zone_capacity = {o.zone_id: o.capacity for o in snapshot.occupancies}

    new_incidents: list[Incident] = []
    now = datetime.now(timezone.utc)

    for intent in scenario_spec.intents:
        zid = intent.target_zone
        if zid not in zone_capacity:
            continue  # Skip invalid zone IDs

        cap = zone_capacity[zid]

        if intent.intent_type == "overwhelm":
            # Map intensity 0.0-1.0 → target occupancy 60%-99% of capacity
            target_pct = 0.60 + (intent.intensity * 0.39)
            target_occs[zid] = int(cap * target_pct)

        elif intent.intent_type == "evacuate":
            # Map intensity 0.0-1.0 → target occupancy 5%-40% of capacity
            target_pct = 0.40 - (intent.intensity * 0.35)
            target_occs[zid] = max(0, int(cap * target_pct))

        elif intent.intent_type == "incident_inject":
            # Determine severity from intensity
            if intent.intensity >= 0.8:
                severity = "critical"
            elif intent.intensity >= 0.6:
                severity = "high"
            elif intent.intensity >= 0.3:
                severity = "medium"
            else:
                severity = "low"

            new_incidents.append(
                Incident(
                    id=f"inc_genai_{zid}_{int(now.timestamp())}",
                    zone_id=zid,
                    type="security",
                    severity=severity,
                    reported_at=now,
                )
            )

        elif intent.intent_type == "capacity_shift":
            # Shift crowd toward this zone (increase by intensity * 30%)
            boost = int(cap * intent.intensity * 0.30)
            target_occs[zid] = min(cap * 3, source_occs.get(zid, 0) + boost)

    # Step 3: Set up intervention state manager for progressive crowd shift
    state.intervention_manager = InterventionStateManager(
        approved_at=time.time(),
        source_occupancies=source_occs,
        target_occupancies=target_occs,
        duration=float(scenario_spec.estimated_duration_seconds),
    )

    # Step 4: If incidents were generated, patch the snapshot
    if new_incidents:
        patched_occupancies = []
        for occ in snapshot.occupancies:
            if occ.zone_id in target_occs:
                patched_occupancies.append(
                    Occupancy(
                        zone_id=occ.zone_id,
                        count=target_occs[occ.zone_id],
                        capacity=occ.capacity,
                        pct_capacity=occ.pct_capacity,
                        trend=occ.trend,
                    )
                )
            else:
                patched_occupancies.append(occ)

        patched_snapshot = VenueSnapshot(
            timestamp=now,
            zones=snapshot.zones,
            occupancies=patched_occupancies,
            incidents=list(snapshot.incidents) + new_incidents,
            staff=snapshot.staff,
        )
        adapter.set_override_snapshot(patched_snapshot)

    state.cached_reason_output = None

    return GenerateScenarioResponse(
        status="success",
        scenario=scenario_spec,
        message=f"AI scenario '{scenario_spec.name}' generated and applied. {scenario_spec.narrative}",
    )
