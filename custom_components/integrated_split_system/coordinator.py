"""Per-room runtime coordinator (M1: no physical actuator)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PROFILE_ID, DEFAULT_PROFILE_ID


class IntegratedSplitSystemCoordinator:
    """Holds per-entry runtime state for one room."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.boost_active = False
        self.profile_id = entry.data.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID)

    async def async_set_boost_active(self, active: bool) -> None:
        """Record boost state only (M1: no physical writes)."""
        self.boost_active = active

    def set_boost_active(self, active: bool) -> None:
        """Sync boost state helper for tests."""
        self.boost_active = active
