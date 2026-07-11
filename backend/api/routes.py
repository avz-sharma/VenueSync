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
from backend.preprocessor.core import preprocess_snapshot
from backend.reasoning.core import generate_actions
from backend.schemas import VenueSnapshot
from backend.schemas.reasoning import ActionRecommendation, ReasoningCycleOutput
from shared.schemas.domain import Incident, Occupancy

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Global State & Cache
# ---------------------------------------------------------------------------

_active_adapter: DataSourceAdapter | None = None
_reason_lock = asyncio.Lock()

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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/snapshot", response_model=VenueSnapshot)
async def get_snapshot() -> VenueSnapshot:
    """Fetch the current canonical VenueSnapshot from the active Data Adapter."""
    adapter = get_active_adapter()
    return await adapter.get_snapshot()


@router.post("/reason", response_model=ReasoningCycleOutput)
async def run_reason() -> ReasoningCycleOutput:
    """Trigger the Reasoning Engine with a 15-second debounce mechanism.

    If a request is received within 15 seconds of the last execution, the cached
    ReasoningCycleOutput is returned instead of calling the LLM again.
    """
    global _last_reason_time, _cached_reason_output

    async with _reason_lock:
        current_time = time.time()
        if _cached_reason_output is not None and (current_time - _last_reason_time) < 15.0:
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
        logger.info(f"Action approval request for {action_id} ignored (already approved)")
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

    # Clear reasoning cache so the evaluation can immediately reason on this new state
    global _cached_reason_output
    _cached_reason_output = None

    logger.info("Loaded tense demo scenario (gate_north critical medical incident)")

    return LoadScenarioResponse(
        status="success",
        message="Tense demo scenario loaded successfully. 'gate_north' is at 98% capacity with an active medical incident.",
    )
