import asyncio
import time
from typing import Dict, Any, Optional
from fastapi import Request

from backend.adapters.base import DataSourceAdapter
from backend.preprocessor.intervention import InterventionStateManager
from backend.schemas.reasoning import (
    ActionRecommendation,
    ReasoningCycleOutput,
    OperatorQueryResponse,
)


class VenueSyncState:
    """State container for the FastAPI application to encapsulate all mutable global state."""

    def __init__(self):
        self.active_adapter: Optional[DataSourceAdapter] = None
        self.reason_lock = asyncio.Lock()
        self.intervention_manager: Optional[InterventionStateManager] = None

        # Debounce cache for LLM reasoning cycle
        self.last_reason_time: float = 0.0
        self.cached_reason_output: Optional[ReasoningCycleOutput] = None

        # Known recommendations from reasoning engine
        self.known_actions: Dict[str, ActionRecommendation] = {}

        # Approved actions (for idempotency tracking)
        self.approved_actions: Dict[str, Dict[str, Any]] = {}

        # Operator query throttle
        self.last_operator_query_time: float = 0.0
        self.cached_operator_response: Optional[OperatorQueryResponse] = None

    def get_adapter(self) -> DataSourceAdapter:
        """Retrieve or lazily initialize the active data source adapter."""
        if self.active_adapter is None:
            import os
            import logging
            from backend.adapters import get_adapter

            logger = logging.getLogger(__name__)
            source = os.environ.get("DATA_SOURCE", "synthetic")
            logger.info(f"Initializing active data source adapter: {source}")
            self.active_adapter = get_adapter(source)
        return self.active_adapter

    def prune_expired_actions(self):
        """Removes historical recommendations older than 4 hours to prevent memory exhaustion leaks."""
        now_ts = time.time()
        max_age = 14400.0  # 4 hours in seconds

        # Evict items safely from registry collections
        expired_known = [
            k
            for k, v in self.known_actions.items()
            if getattr(v, "created_at", 0) < now_ts - max_age
        ]
        for k in expired_known:
            self.known_actions.pop(k, None)

        expired_approved = [
            k
            for k, v in self.approved_actions.items()
            if v.get("timestamp", 0) < now_ts - max_age
        ]
        for k in expired_approved:
            self.approved_actions.pop(k, None)


def get_app_state(request: Request) -> VenueSyncState:
    """FastAPI dependency to retrieve the VenueSyncState container."""
    return request.app.state.venue_sync
