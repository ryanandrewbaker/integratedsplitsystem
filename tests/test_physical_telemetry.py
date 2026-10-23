"""Read-only physical climate telemetry handling (M1)."""

from __future__ import annotations

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN, HVACMode, SERVICE_SET_TEMPERATURE
from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_conversion import TemperatureConverter

from custom_components.integrated_split_system.const import MINIMUM_TARGET_SEPARATION_C

from .conftest import (
    build_config_entry_data,
    climate_entities_for_entry,
    get_virtual_climate_entity,
    setup_config_entry,
    track_climate_service_calls,
)


def _configure_hass_fahrenheit(hass) -> None:
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

    hass.config.units = US_CUSTOMARY_SYSTEM


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


async def test_fahrenheit_physical_explicit_unit_converted_to_celsius(
    hass, physical_climate_factory
) -> None:
    """Physical entity declares Fahrenheit explicitly (metadata present)."""
    physical_id = await physical_climate_factory(
        "climate.fahrenheit_ac",
        unique_id="fahrenheit_ac",
        attributes={
            "temperature_unit": UnitOfTemperature.FAHRENHEIT,
            "current_temperature": 68.0,
            "temperature": 70.0,
        },
    )
    with track_climate_service_calls(hass) as calls:
        entry = await setup_config_entry(
            hass,
            build_config_entry_data(
                physical_climate_entity_id=physical_id,
                room_name="Fahrenheit Room",
            ),
            entry_id="fahrenheit_room_explicit",
        )
        await hass.async_block_till_done()

    entity = get_virtual_climate_entity(hass, entry.entry_id)
    assert entity.current_temperature == 20.0
    assert not any(
        c[2].get("entity_id") == physical_id for c in calls
    )


async def test_fahrenheit_hass_unit_without_physical_unit_metadata(
    hass, physical_climate_factory
) -> None:
    """HA user unit Fahrenheit; physical climate omits unit metadata (HA 2026.10)."""
    _configure_hass_fahrenheit(hass)

    physical_id = await physical_climate_factory(
        "climate.us_physical_ac",
        unique_id="us_physical_ac",
        attributes={
            "current_temperature": 68.0,
            "min_temp": 60.0,
            "max_temp": 86.0,
            "temperature": 70.0,
        },
    )

    with track_climate_service_calls(hass) as calls:
        entry = await setup_config_entry(
            hass,
            build_config_entry_data(
                physical_climate_entity_id=physical_id,
                room_name="US Room",
            ),
            entry_id="fahrenheit_hass_implicit",
        )
        await hass.async_block_till_done()

    entity = get_virtual_climate_entity(hass, entry.entry_id)
    climate_id = climate_entities_for_entry(hass, entry.entry_id)[0]
    state = hass.states.get(climate_id)
    assert state is not None

    assert entity.current_temperature == 20.0
    assert entity.min_temp == TemperatureConverter.convert(
        60.0, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
    )
    assert entity.max_temp == TemperatureConverter.convert(
        86.0, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
    )

    center_c = TemperatureConverter.convert(
        70.0, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
    )
    assert entity.target_temperature_low is not None
    assert entity.target_temperature_high is not None
    assert (
        entity.target_temperature_high - entity.target_temperature_low
        >= MINIMUM_TARGET_SEPARATION_C
    )
    assert abs(
        (entity.target_temperature_low + entity.target_temperature_high) / 2 - center_c
    ) < 1.5

    display_current = TemperatureConverter.convert(
        20.0, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT
    )
    assert state.attributes["current_temperature"] == display_current
    assert state.attributes["target_temp_low"] == TemperatureConverter.convert(
        entity.target_temperature_low,
        UnitOfTemperature.CELSIUS,
        UnitOfTemperature.FAHRENHEIT,
    )

    assert not any(c[2].get("entity_id") == physical_id for c in calls)


async def test_celsius_hass_still_interprets_celsius_physical(hass, kitchen_physical_climate: str) -> None:
    """Default metric HA install: unchanged Celsius physical readings."""
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="celsius_regression",
    )
    entity = get_virtual_climate_entity(hass, entry.entry_id)
    assert entity.current_temperature == 22.0
