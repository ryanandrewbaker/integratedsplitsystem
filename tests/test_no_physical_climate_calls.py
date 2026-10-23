"""FR-07 acceptance: stable setup lifecycle must not call physical climate services."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .conftest import (
    build_config_entry_data,
    setup_config_entry,
    track_climate_service_calls,
)
from custom_components.integrated_split_system.const import SENSIBO_CONTROLLER_UNKNOWN


def _physical_entity_ids_from_calls(
    calls: list[tuple[str, str, dict]],
    physical_entity_ids: set[str],
) -> list[tuple[str, str, dict]]:
    """Return climate service calls that target mock physical climates."""
    matched: list[tuple[str, str, dict]] = []
    for domain, service, service_data in calls:
        if domain != "climate":
            continue
        entity_id = service_data.get("entity_id")
        if entity_id is None:
            continue
        targets = entity_id if isinstance(entity_id, list) else [entity_id]
        if set(targets) & physical_entity_ids:
            matched.append((domain, service, service_data))
    return matched


async def test_setup_reload_unload_no_physical_climate_service_calls(
    hass: HomeAssistant,
    kitchen_physical_climate: str,
    family_room_physical_climate: str,
) -> None:
    """Setup, reload, and unload two entries without physical climate.* writes."""
    physical_ids = {kitchen_physical_climate, family_room_physical_climate}

    with track_climate_service_calls(hass) as calls:
        entry_kitchen = await setup_config_entry(
            hass,
            build_config_entry_data(
                physical_climate_entity_id=kitchen_physical_climate,
                room_name="Kitchen",
                profile_id="kitchen",
                sensibo_controller_type=SENSIBO_CONTROLLER_UNKNOWN,
            ),
            entry_id="no_calls_kitchen",
        )
        entry_family = await setup_config_entry(
            hass,
            build_config_entry_data(
                physical_climate_entity_id=family_room_physical_climate,
                room_name="Family Room",
                profile_id="upstairs",
                sensibo_controller_type=SENSIBO_CONTROLLER_UNKNOWN,
            ),
            entry_id="no_calls_family",
        )
        await hass.async_block_till_done()

        assert await hass.config_entries.async_reload(entry_kitchen.entry_id)
        assert await hass.config_entries.async_reload(entry_family.entry_id)
        await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry_kitchen.entry_id)
        assert await hass.config_entries.async_unload(entry_family.entry_id)
        await hass.async_block_till_done()

    physical_calls = _physical_entity_ids_from_calls(calls, physical_ids)
    assert physical_calls == []

    assert entry_kitchen.state is ConfigEntryState.NOT_LOADED
    assert entry_family.state is ConfigEntryState.NOT_LOADED
