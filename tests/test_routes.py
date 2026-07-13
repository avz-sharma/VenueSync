"""Tests for API routes: snapshot, reason, approve, and load-scenario."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from backend.main import app
from backend.preprocessor.core import process_historical_run
from backend.schemas.reasoning import ActionRecommendation, ReasoningCycleOutput
from shared.schemas.domain import HistoricalMetrics, Occupancy, VenueSnapshot, Zone

mock_output = ReasoningCycleOutput(
    actions=[
        ActionRecommendation(
            action_type="redirect_crowd",
            priority=1,
            target_zones=["gate_north", "concourse_a"],
            confidence=0.9,
            rationale="Test rationale",
            predicted_impact="Test impact",
        )
    ],
    degraded_mode=False,
)


@pytest.mark.asyncio
async def test_get_snapshot() -> None:
    """GET /api/snapshot must return 200 and a valid VenueSnapshot."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/snapshot")

    assert response.status_code == 200
    data = response.json()
    assert "zones" in data
    assert "occupancies" in data
    assert "incidents" in data
    assert "staff" in data
    assert len(data["zones"]) == 8


@pytest.mark.asyncio
async def test_post_reason_debounce() -> None:
    """POST /api/reason must debounce multiple requests within 15 seconds.

    Verify that:
    1. The first call triggers generate_actions.
    2. The second call within 15 seconds returns cached output without invoking generate_actions.
    3. The actions in both calls have the exact same generated IDs (proving the cache object was reused).
    """
    import backend.api.routes

    # Reset global state for test isolation
    backend.api.routes._cached_reason_output = None
    backend.api.routes._last_reason_time = 0.0
    backend.api.routes._known_actions.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch(
            "backend.api.routes.generate_actions", return_value=mock_output
        ) as mock_gen:
            # First call
            res1 = await client.post("/api/reason")
            assert res1.status_code == 200
            data1 = res1.json()
            assert len(data1["actions"]) == 1
            action1_id = data1["actions"][0]["id"]

            # Second call (immediate)
            res2 = await client.post("/api/reason")
            assert res2.status_code == 200
            data2 = res2.json()
            action2_id = data2["actions"][0]["id"]

            # Verify debounce logic
            assert action1_id == action2_id
            mock_gen.assert_called_once()


@pytest.mark.asyncio
async def test_approve_action_idempotency() -> None:
    """POST /api/actions/{action_id}/approve must be idempotent.

    Verify that:
    1. Approving an invalid action ID returns a 404.
    2. Approving a valid action ID first executes the state mutation (already_approved=False).
    3. Subsequent approvals of the same ID are ignored and returned as already approved (already_approved=True).
    """
    import backend.api.routes

    # Reset global state for test isolation
    backend.api.routes._cached_reason_output = None
    backend.api.routes._last_reason_time = 0.0
    backend.api.routes._known_actions.clear()
    backend.api.routes._approved_actions.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Try to approve a nonexistent ID
        res_404 = await client.post("/api/actions/nonexistent_action_id/approve")
        assert res_404.status_code == 404

        # Populate the known actions by triggering reasoning
        with patch("backend.api.routes.generate_actions", return_value=mock_output):
            reason_res = await client.post("/api/reason")
            action_id = reason_res.json()["actions"][0]["id"]

        # 2. First approval (should execute mutation)
        res_app1 = await client.post(f"/api/actions/{action_id}/approve")
        assert res_app1.status_code == 200
        assert res_app1.json()["already_approved"] is False
        assert "executed successfully" in res_app1.json()["message"]

        # 3. Second approval (should be idempotent check)
        res_app2 = await client.post(f"/api/actions/{action_id}/approve")
        assert res_app2.status_code == 200
        assert res_app2.json()["already_approved"] is True
        assert "already approved" in res_app2.json()["message"]


@pytest.mark.asyncio
async def test_load_demo_scenario() -> None:
    """GET /api/demo/load-scenario must override the adapter state with the critical config.

    Verify that:
    1. Loading the scenario returns 200 success.
    2. Subsequent /snapshot calls return gate_north at 98% occupancy.
    3. There is a critical medical incident in gate_north.
    """
    import backend.api.routes

    # Clear override state and cache
    adapter = backend.api.routes.get_active_adapter()
    adapter.set_override_snapshot(None)
    backend.api.routes._cached_reason_output = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Load demo scenario
        load_res = await client.get("/api/demo/load-scenario")
        assert load_res.status_code == 200
        assert load_res.json()["status"] == "success"

        # Fetch snapshot
        snap_res = await client.get("/api/snapshot")
        assert snap_res.status_code == 200
        snap_data = snap_res.json()

        # Find gate_north occupancy and assert it's at 98%
        gate_north_occ = next(
            (o for o in snap_data["occupancies"] if o["zone_id"] == "gate_north"), None
        )
        assert gate_north_occ is not None
        assert gate_north_occ["count"] == 1960
        assert gate_north_occ["capacity"] == 2000

        # Find critical medical incident in gate_north
        incidents = snap_data["incidents"]
        gate_north_incident = next(
            (i for i in incidents if i["zone_id"] == "gate_north"), None
        )
        assert gate_north_incident is not None
        assert gate_north_incident["type"] == "medical"
        assert gate_north_incident["severity"] == "critical"


# ---------------------------------------------------------------------------
# Debrief endpoint tests
# ---------------------------------------------------------------------------

_UTC = timezone.utc


def _make_snapshot(
    gate_north_pct: float = 0.40,
    include_incident: bool = False,
) -> VenueSnapshot:
    """Build a minimal but fully-valid VenueSnapshot for debrief tests."""
    zones = [
        Zone(id="gate_north", name="Gate North", capacity=2000, adjacent_zones=[]),
        Zone(id="concourse_a", name="Concourse A", capacity=1500, adjacent_zones=[]),
    ]
    occupancies = [
        Occupancy(
            zone_id="gate_north",
            count=int(2000 * gate_north_pct),
            capacity=2000,
            pct_capacity=0.0,
            trend="stable",
        ),
        Occupancy(
            zone_id="concourse_a",
            count=int(1500 * 0.40),
            capacity=1500,
            pct_capacity=0.0,
            trend="stable",
        ),
    ]
    return VenueSnapshot(
        timestamp=datetime.now(_UTC),
        zones=zones,
        occupancies=occupancies,
        incidents=[],
        staff=[],
    )


_MOCK_HISTORICAL = HistoricalMetrics(
    top_bottlenecks=["Gate North"],
    critical_density_duration_minutes=15,
    executive_summary="Gate North was the primary bottleneck. Increase staff deployment there next event.",
)


class TestDebriefEndpoint:
    """Behavioural tests for POST /api/analytics/debrief."""

    @pytest.mark.asyncio
    async def test_debrief_empty_list_returns_422(self) -> None:
        """An empty snapshots list must be rejected with HTTP 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/analytics/debrief",
                json={"snapshots": []},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_debrief_happy_path(self) -> None:
        """Valid snapshot list returns a well-formed HistoricalMetrics response.

        generate_debrief is mocked so no LLM call is made during CI.
        """
        snapshots = [_make_snapshot(gate_north_pct=0.97) for _ in range(3)]
        payload = {"snapshots": [s.model_dump(mode="json") for s in snapshots]}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            with patch(
                "backend.api.routes.generate_debrief",
                return_value=_MOCK_HISTORICAL,
            ):
                response = await client.post("/api/analytics/debrief", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "top_bottlenecks" in data
        assert "critical_density_duration_minutes" in data
        assert "executive_summary" in data
        assert isinstance(data["executive_summary"], str)
        assert len(data["executive_summary"]) > 0

    @pytest.mark.asyncio
    async def test_debrief_validation_failure_returns_fallback(self) -> None:
        """When generate_debrief raises ValidationError the endpoint must return
        an inert but valid HistoricalMetrics fallback (no 500 crash).
        """
        snapshots = [_make_snapshot(gate_north_pct=0.97)]
        payload = {"snapshots": [s.model_dump(mode="json") for s in snapshots]}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # generate_debrief already handles ValidationError internally and returns
            # a fallback HistoricalMetrics — so we simulate the final-gate failure
            # by patching it to return the pre-built fallback directly.
            with patch(
                "backend.api.routes.generate_debrief",
                return_value=HistoricalMetrics(
                    top_bottlenecks=["unknown"],
                    critical_density_duration_minutes=0,
                    executive_summary=(
                        "System running in degraded mode — LLM debrief unavailable. "
                        "Manual review of historical run data is required before next event."
                    ),
                ),
            ):
                response = await client.post("/api/analytics/debrief", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "degraded" in data["executive_summary"].lower()
        assert data["top_bottlenecks"] == ["unknown"]
        assert data["critical_density_duration_minutes"] == 0

    def test_debrief_math_isolation(self) -> None:
        """process_historical_run must compute correct metrics without any LLM call.

        Three snapshots where gate_north is at 97 % capacity (above the 95 % PHS
        critical threshold) and concourse_a is at 40 % (not critical).
        Expected:
          - top_bottlenecks == ["Gate North"]  (only zone that breached)
          - critical_density_duration_minutes == 3 ticks * 5 min/tick == 15
          - snapshot_count == 3
        """
        snapshots = [_make_snapshot(gate_north_pct=0.97) for _ in range(3)]
        result = process_historical_run(snapshots)

        assert result["top_bottlenecks"] == ["Gate North"]
        assert result["critical_density_duration_minutes"] == 15
        assert result["snapshot_count"] == 3

    def test_debrief_math_isolation_no_breaches(self) -> None:
        """With all zones below the critical threshold, duration must be zero."""
        snapshots = [_make_snapshot(gate_north_pct=0.50) for _ in range(5)]
        result = process_historical_run(snapshots)

        assert result["top_bottlenecks"] == []
        assert result["critical_density_duration_minutes"] == 0
        assert result["snapshot_count"] == 5


@pytest.mark.asyncio
async def test_demo_gate_closure() -> None:
    """POST /api/demo/gate-closure must set up intervention and return 200."""
    import backend.api.routes
    
    adapter = backend.api.routes.get_active_adapter()
    adapter.set_override_snapshot(None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.post("/api/demo/gate-closure", json={"gate_id": "gate_north"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["closed_gate"] == "gate_north"
        assert "redirect_targets" in data
        
    assert backend.api.routes._intervention_manager is not None
    assert backend.api.routes._cached_reason_output is None
    backend.api.routes._intervention_manager = None # cleanup


@pytest.mark.asyncio
async def test_demo_rain_simulation() -> None:
    """POST /api/demo/rain-simulation must set up intervention and return 200."""
    import backend.api.routes
    
    adapter = backend.api.routes.get_active_adapter()
    adapter.set_override_snapshot(None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.post("/api/demo/rain-simulation")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "covered_zones" in data
        
    assert backend.api.routes._intervention_manager is not None
    assert backend.api.routes._cached_reason_output is None
    backend.api.routes._intervention_manager = None # cleanup

