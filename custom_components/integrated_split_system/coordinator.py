"""Per-room runtime coordinator (M1: no physical actuator)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .entry_helpers import get_profile_id, get_sensibo_controller_type


class IntegratedSplitSystemCoordinator:
    """Holds per-entry runtime state for one room."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.boost_active = False
        self.refresh_from_entry(entry)

    def refresh_from_entry(self, entry: ConfigEntry) -> None:
        """Reload option-backed fields after options change or reload."""
        self.entry = entry
        self.profile_id = get_profile_id(entry)
        self.sensibo_controller_type = get_sensibo_controller_type(entry)

    async def async_set_boost_active(self, active: bool) -> None:
        """Record boost state only (M1: no physical writes)."""
        self.boost_active = active

    def set_boost_active(self, active: bool) -> None:
        """Sync boost state helper for tests."""
        self.boost_active = active
