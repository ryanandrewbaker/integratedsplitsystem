"""FR-01: multi-instance setup, unload, and reload."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .conftest import (
    build_config_entry_data,
    climate_entities_for_entry,
    setup_config_entry,
    track_climate_service_calls,
)
from custom_components.integrated_split_system.const import (
    CONF_PHYSICAL_CLIMATE_ENTITY_ID,
    CONF_PROFILE_ID,
    CONF_ROOM_NAME,
    CONF_SENSIBO_CONTROLLER_TYPE,
    DEFAULT_PROFILE_ID,
    SENSIBO_CONTROLLER_UNKNOWN,
)


async def test_two_entries_setup_unload_and_reload(
    hass: HomeAssistant,
    kitchen_physical_climate: str,
    family_room_physical_climate: str,
) -> None:
    """Two distinct physical climates: setup, reload both, unload both (FR-01)."""
    entry_kitchen = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
            profile_id="kitchen",
            sensibo_controller_type=SENSIBO_CONTROLLER_UNKNOWN,
        ),
        entry_id="kitchen_entry",
    )
    entry_family = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=family_room_physical_climate,
            room_name="Family Room",
            profile_id="upstairs",
            sensibo_controller_type=SENSIBO_CONTROLLER_UNKNOWN,
        ),
        entry_id="family_entry",
    )

    assert entry_kitchen.state is ConfigEntryState.LOADED
    assert entry_family.state is ConfigEntryState.LOADED

    kitchen_climates = climate_entities_for_entry(hass, entry_kitchen.entry_id)
    family_climates = climate_entities_for_entry(hass, entry_family.entry_id)
    assert len(kitchen_climates) == 1
    assert len(family_climates) == 1
    assert kitchen_climates[0] != family_climates[0]

    with track_climate_service_calls(hass):
        assert await hass.config_entries.async_reload(entry_kitchen.entry_id)
        assert await hass.config_entries.async_reload(entry_family.entry_id)
        await hass.async_block_till_done()

    reloaded_kitchen = hass.config_entries.async_get_entry(entry_kitchen.entry_id)
    reloaded_family = hass.config_entries.async_get_entry(entry_family.entry_id)
    assert reloaded_kitchen is not None and reloaded_kitchen.state is ConfigEntryState.LOADED
    assert reloaded_family is not None and reloaded_family.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry_kitchen.entry_id)
    assert await hass.config_entries.async_unload(entry_family.entry_id)
    await hass.async_block_till_done()

    assert hass.config_entries.async_get_entry(entry_kitchen.entry_id).state is ConfigEntryState.NOT_LOADED
    assert hass.config_entries.async_get_entry(entry_family.entry_id).state is ConfigEntryState.NOT_LOADED


async def test_config_entry_data_round_trip_after_reload(
    hass: HomeAssistant,
    kitchen_physical_climate: str,
) -> None:
    """Reload preserves FR-01 config entry data keys."""
    data = build_config_entry_data(
        physical_climate_entity_id=kitchen_physical_climate,
        room_name="Kitchen",
        profile_id=DEFAULT_PROFILE_ID,
        sensibo_controller_type=SENSIBO_CONTROLLER_UNKNOWN,
    )
    entry = await setup_config_entry(hass, data, entry_id="round_trip_entry")

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    loaded = hass.config_entries.async_get_entry(entry.entry_id)
    assert loaded is not None
    assert loaded.data[CONF_PHYSICAL_CLIMATE_ENTITY_ID] == kitchen_physical_climate
    assert loaded.data[CONF_ROOM_NAME] == "Kitchen"
    assert loaded.data[CONF_PROFILE_ID] == DEFAULT_PROFILE_ID
    assert loaded.data[CONF_SENSIBO_CONTROLLER_TYPE] == SENSIBO_CONTROLLER_UNKNOWN
