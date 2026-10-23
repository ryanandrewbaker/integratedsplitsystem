"""Lightweight reusable connected-AC equipment profiles (M1 store only)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DEFAULT_PROFILE_ID, DOMAIN, STORAGE_PROFILES_KEY, STORAGE_PROFILES_VERSION

_GENERIC_PROFILE: dict[str, Any] = {
    "id": DEFAULT_PROFILE_ID,
    "name": "Generic / default",
    "shared": True,
}


class EquipmentProfileStore:
    """Persist shared equipment profiles; generic profile is always available."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store = Store(
            hass,
            STORAGE_PROFILES_VERSION,
            STORAGE_PROFILES_KEY,
        )
        self._profiles: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        profiles: dict[str, dict[str, Any]] = {}
        if isinstance(data, dict) and isinstance(data.get("profiles"), dict):
            profiles = dict(data["profiles"])
        profiles[DEFAULT_PROFILE_ID] = dict(_GENERIC_PROFILE)
        self._profiles = profiles
        await self._persist()

    async def _persist(self) -> None:
        await self._store.async_save({"profiles": self._profiles})

    @callback
    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        return self._profiles.get(profile_id)

    @callback
    def list_profiles(self) -> list[dict[str, Any]]:
        return list(self._profiles.values())

    async def async_create_profile(self, profile_id: str, name: str) -> dict[str, Any]:
        profile = {"id": profile_id, "name": name, "shared": True}
        self._profiles[profile_id] = profile
        await self._persist()
        return profile

    async def async_delete_profile(self, profile_id: str) -> bool:
        if profile_id == DEFAULT_PROFILE_ID:
            return False
        if profile_id not in self._profiles:
            return False
        del self._profiles[profile_id]
        await self._persist()
        return True

    def profiles_in_use(self, hass: HomeAssistant) -> set[str]:
        """Profile IDs referenced by any config entry."""
        in_use: set[str] = set()
        from .const import CONF_PROFILE_ID  # local import avoids circular

        for entry in hass.config_entries.async_entries(DOMAIN):
            pid = entry.data.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID)
            in_use.add(pid)
        return in_use
