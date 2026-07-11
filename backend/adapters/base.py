"""VenueSync — Data Source Adapter Interface.

Defines the abstract contract that all data source implementations must fulfill.
This ensures Rule A compliance: the reasoning engine never touches raw data,
only normalized VenueSnapshot objects emitted by adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared.schemas.domain import Staff, VenueSnapshot, Zone


class DataSourceAdapter(ABC):
    """Abstract base class for all venue data sources.

    Implementations must normalize their source data into the Canonical Data
    Schema defined in ``shared.schemas.domain``.  The reasoning engine imports
    only from this interface — never from concrete adapter implementations
    (Rule A).

    Methods
    -------
    get_snapshot
        Return a complete point-in-time venue state.
    get_venue_graph
        Return the venue's zone topology with adjacency information.
    get_staff_roster
        Return the current staff roster.
    """

    def set_override_snapshot(self, snapshot: VenueSnapshot | None) -> None:
        """Override the adapter's snapshot state (used for demo scenarios)."""
        pass

    @abstractmethod
    async def get_snapshot(self) -> VenueSnapshot:
        """Return a complete point-in-time venue state snapshot.

        Each call should reflect the current (or simulated) state of the venue.
        Timestamps must be timezone-aware.
        """
        ...

    @abstractmethod
    async def get_venue_graph(self) -> list[Zone]:
        """Return the venue's zone topology.

        The returned zones include adjacency information for graph-based
        analysis (e.g., crowd flow modeling, evacuation routing).
        """
        ...

    @abstractmethod
    async def get_staff_roster(self) -> list[Staff]:
        """Return the current staff roster with zone assignments and statuses."""
        ...
