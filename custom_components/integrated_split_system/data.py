"""Runtime data attached to each config entry."""

from __future__ import annotations

from dataclasses import dataclass

from .coordinator import IntegratedSplitSystemCoordinator


@dataclass
class IntegratedSplitSystemRuntimeData:
    """Config entry runtime_data container."""

    coordinator: IntegratedSplitSystemCoordinator
