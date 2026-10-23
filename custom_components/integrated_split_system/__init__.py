"""Integrated Split System custom integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_PHYSICAL_CLIMATE_ENTITY_ID,
    CONF_PROFILE_ID,
    DEFAULT_PROFILE_ID,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import IntegratedSplitSystemCoordinator
from .data import IntegratedSplitSystemRuntimeData
from .equipment_profile import EquipmentProfileStore

_LOGGER = logging.getLogger(__name__)


def _physical_climate_in_use(hass: HomeAssistant, physical: str, exclude_entry_id: str) -> bool:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == exclude_entry_id:
            continue
        if entry.data.get(CONF_PHYSICAL_CLIMATE_ENTITY_ID) == physical:
            return True
    return False


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Integrated Split System domain."""
    hass.data.setdefault(DOMAIN, {})
    if "profiles" not in hass.data[DOMAIN]:
        store = EquipmentProfileStore(hass)
        await store.async_load()
        hass.data[DOMAIN]["profiles"] = store
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Integrated Split System from a config entry."""
    physical = entry.data[CONF_PHYSICAL_CLIMATE_ENTITY_ID]
    if _physical_climate_in_use(hass, physical, entry.entry_id):
        _LOGGER.error(
            "Physical climate %s is already bound to another entry; refusing setup",
            physical,
        )
        return False

    await async_setup(hass, {})

    profile_id = entry.data.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID)
    store: EquipmentProfileStore = hass.data[DOMAIN]["profiles"]
    if store.get_profile(profile_id) is None:
        await store.async_create_profile(profile_id, profile_id.replace("_", " ").title())

    coordinator = IntegratedSplitSystemCoordinator(hass, entry)
    entry.runtime_data = IntegratedSplitSystemRuntimeData(coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
