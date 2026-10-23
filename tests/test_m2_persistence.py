"""M2 persistence and restart-safe user intent."""

from __future__ import annotations

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE, HVACMode

from .conftest import (
    build_config_entry_data,
    climate_entities_for_entry,
    setup_config_entry,
    track_climate_service_calls,
)


async def test_fresh_entry_defaults_off(hass, kitchen_physical_climate: str) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="fresh_off",
    )
    climate_id = climate_entities_for_entry(hass, entry.entry_id)[0]
    assert hass.states.get(climate_id).state == HVACMode.OFF


async def test_reload_preserves_user_targets_and_mode(hass, kitchen_physical_climate: str) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="persist_reload",
    )
    climate_id = climate_entities_for_entry(hass, entry.entry_id)[0]

    with track_climate_service_calls(hass) as calls:
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {
                "entity_id": climate_id,
                "target_temp_low": 19.0,
                "target_temp_high": 25.0,
            },
            blocking=True,
        )
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            "set_hvac_mode",
            {"entity_id": climate_id, "hvac_mode": HVACMode.HEAT_COOL},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(climate_id)
    assert state is not None
    assert state.state == HVACMode.HEAT_COOL
    assert state.attributes["target_temp_low"] == 19.0
    assert state.attributes["target_temp_high"] == 25.0
    assert not any(c[2].get("entity_id") == kitchen_physical_climate for c in calls)
