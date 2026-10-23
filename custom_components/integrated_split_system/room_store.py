"""Per-room persisted user intent (M2: targets and HVAC mode)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_ROOM_STATE_KEY, STORAGE_ROOM_STATE_VERSION

_DEFAULT_STATE: dict[str, Any] = {
    "target_temp_low": None,
    "target_temp_high": None,
    "hvac_mode": HVACMode.OFF,
    "controller_state": "idle",
    "controller_direction": "heat",
    "user_configured": False,
}


class RoomStateStore:
    """Persist comfort targets and virtual HVAC mode per config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._store = Store(
            hass,
            STORAGE_ROOM_STATE_VERSION,
            f"{STORAGE_ROOM_STATE_KEY}.{entry_id}",
        )
        self._data: dict[str, Any] = dict(_DEFAULT_STATE)

    async def async_load(self) -> dict[str, Any]:
        loaded = await self._store.async_load()
        if isinstance(loaded, dict):
            self._data = {**_DEFAULT_STATE, **loaded}
        return self._data

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    async def async_save(self) -> None:
        await self._store.async_save(self._data)

    async def async_update(self, **fields: Any) -> None:
        changed = False
        for key, value in fields.items():
            if self._data.get(key) != value:
                self._data[key] = value
                changed = True
        if changed:
            await self.async_save()
