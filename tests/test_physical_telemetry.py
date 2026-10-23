"""Read-only physical climate telemetry handling (M1)."""

from __future__ import annotations

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN, HVACMode, SERVICE_SET_TEMPERATURE
from homeassistant.const import UnitOfTemperature

from .conftest import (
    build_config_entry_data,
    climate_entities_for_entry,
    setup_config_entry,
    track_climate_service_calls,
)


async def test_invalid_current_temperature_does_not_crash_listener(
    hass, kitchen_physical_climate: str
) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="bad_current",
    )
    climate_id = climate_entities_for_entry(hass, entry.entry_id)[0]

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
    await hass.async_block_till_done()

    with track_climate_service_calls(hass):
        hass.states.async_set(
            kitchen_physical_climate,
            HVACMode.HEAT_COOL,
            {
                **hass.states.get(kitchen_physical_climate).attributes,
                "current_temperature": "unknown",
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get(climate_id)
    assert state is not None
    assert state.attributes["target_temp_low"] == 19.0
    assert state.attributes["target_temp_high"] == 25.0


async def test_fahrenheit_physical_current_converted_to_celsius(
    hass, physical_climate_factory
) -> None:
    physical_id = await physical_climate_factory(
        "climate.fahrenheit_ac",
        unique_id="fahrenheit_ac",
        attributes={
            "temperature_unit": UnitOfTemperature.FAHRENHEIT,
            "current_temperature": 68.0,
            "temperature": 70.0,
        },
    )
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=physical_id,
            room_name="Fahrenheit Room",
        ),
        entry_id="fahrenheit_room",
    )
    climate_id = climate_entities_for_entry(hass, entry.entry_id)[0]
    state = hass.states.get(climate_id)
    assert state is not None
    assert state.attributes["current_temperature"] == 20.0
