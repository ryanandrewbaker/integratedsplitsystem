"""Dual-setpoint virtual temperature updates (M1)."""

from __future__ import annotations

import math

import pytest
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.climate.const import ATTR_TARGET_TEMP_HIGH, ATTR_TARGET_TEMP_LOW
from homeassistant.exceptions import ServiceValidationError

from .conftest import (
    build_config_entry_data,
    climate_entities_for_entry,
    get_virtual_climate_entity,
    setup_config_entry,
    track_climate_service_calls,
)


async def test_low_only_update_preserves_requested_low(hass, kitchen_physical_climate: str) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="low_only",
    )
    entity = get_virtual_climate_entity(hass, entry.entry_id)
    climate_id = climate_entities_for_entry(hass, entry.entry_id)[0]

    with track_climate_service_calls(hass) as calls:
        await entity.async_set_temperature(**{ATTR_TARGET_TEMP_LOW: 25.0})
        await hass.async_block_till_done()

    state = hass.states.get(climate_id)
    assert state.attributes["target_temp_low"] == 25.0
    assert state.attributes["target_temp_high"] == 27.0
    assert not any(c[2].get("entity_id") == kitchen_physical_climate for c in calls)


async def test_high_only_update_preserves_requested_high(hass, kitchen_physical_climate: str) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="high_only",
    )
    entity = get_virtual_climate_entity(hass, entry.entry_id)
    climate_id = climate_entities_for_entry(hass, entry.entry_id)[0]

    with track_climate_service_calls(hass):
        await entity.async_set_temperature(**{ATTR_TARGET_TEMP_HIGH: 19.0})
        await hass.async_block_till_done()

    state = hass.states.get(climate_id)
    assert state.attributes["target_temp_high"] == 19.0
    assert state.attributes["target_temp_low"] == 17.0


async def test_equal_low_and_high_rejected(hass, kitchen_physical_climate: str) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="equal_band",
    )
    climate_id = climate_entities_for_entry(hass, entry.entry_id)[0]

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {
                "entity_id": climate_id,
                "target_temp_low": 21.0,
                "target_temp_high": 21.0,
            },
            blocking=True,
        )


async def test_low_near_max_rejected(hass, kitchen_physical_climate: str) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="near_max",
    )
    entity = get_virtual_climate_entity(hass, entry.entry_id)

    with pytest.raises(ServiceValidationError):
        await entity.async_set_temperature(**{ATTR_TARGET_TEMP_LOW: 29.5})


async def test_invalid_temperature_rejected(hass, kitchen_physical_climate: str) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="invalid_temp",
    )
    entity = get_virtual_climate_entity(hass, entry.entry_id)

    with pytest.raises(ServiceValidationError):
        await entity.async_set_temperature(**{ATTR_TARGET_TEMP_LOW: math.nan})
