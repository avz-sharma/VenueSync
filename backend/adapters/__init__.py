"""VenueSync — Data Source Adapter Registry.

Provides a factory function ``get_adapter()`` to instantiate the correct
adapter based on the ``DATA_SOURCE`` environment variable.

Usage::

    from backend.adapters import get_adapter
    adapter = get_adapter("synthetic")
    snapshot = await adapter.get_snapshot()
"""

from __future__ import annotations

from backend.adapters.base import DataSourceAdapter
from backend.adapters.synthetic import SyntheticAdapter
from backend.adapters.upload import CustomUploadAdapter

_ADAPTER_REGISTRY: dict[str, type[DataSourceAdapter]] = {
    "synthetic": SyntheticAdapter,
    "upload": CustomUploadAdapter,
}


def get_adapter(source: str) -> DataSourceAdapter:
    """Instantiate the appropriate data source adapter.

    Parameters
    ----------
    source
        The data source identifier, typically read from the ``DATA_SOURCE``
        environment variable.  Valid values: ``"synthetic"``, ``"upload"``.

    Returns
    -------
    DataSourceAdapter
        A concrete adapter instance ready for use.

    Raises
    ------
    ValueError
        If *source* is not a registered adapter name.
    """
    adapter_cls: type[DataSourceAdapter] | None = _ADAPTER_REGISTRY.get(source)
    if adapter_cls is None:
        available: str = ", ".join(sorted(_ADAPTER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown data source: '{source}'. Available adapters: {available}"
        )
    return adapter_cls()


__all__: list[str] = [
    "DataSourceAdapter",
    "SyntheticAdapter",
    "CustomUploadAdapter",
    "get_adapter",
]
