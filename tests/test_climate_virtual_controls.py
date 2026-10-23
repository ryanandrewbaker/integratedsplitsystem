"""Virtual climate control surface (M1: no physical writes)."""

from __future__ import annotations

import pytest
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.exceptions import ServiceValidationError

from custom_components.integrated_split_system.const import (
    DEFAULT_PROFILE_ID,
    SENSIBO_CONTROLLER_UNKNOWN,
)

from .conftest import (
    build_config_entry_data,
    climate_entities_for_entry,
    setup_config_entry,
    track_climate_service_calls,
)


async def test_hvac_mode_virtual_only(hass, kitchen_physical_climate: str) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
            profile_id=DEFAULT_PROFILE_ID,
            sensibo_controller_type=SENSIBO_CONTROLLER_UNKNOWN,
        ),
        entry_id="hvac_virtual",
    )
    climate_id = climate_entities_for_entry(hass, entry.entry_id)[0]
    state = hass.states.get(climate_id)
    assert state is not None
    assert set(state.attributes["hvac_modes"]) == {HVACMode.OFF, HVACMode.HEAT_COOL}

    with track_climate_service_calls(hass) as calls:
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {"entity_id": climate_id, "hvac_mode": HVACMode.OFF},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert hass.states.get(climate_id).state == HVACMode.OFF
    assert not any(
        c[2].get("entity_id") == kitchen_physical_climate for c in calls
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {"entity_id": climate_id, "hvac_mode": HVACMode.COOL},
            blocking=True,
        )


async def test_temperature_band_rejects_insufficient_separation(
    hass, kitchen_physical_climate: str
) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="band_sep",
    )
    climate_id = climate_entities_for_entry(hass, entry.entry_id)[0]

    with pytest.raises(ServiceValidationError):
        with track_climate_service_calls(hass):
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


async def test_physical_state_does_not_overwrite_user_targets(
    hass, kitchen_physical_climate: str
) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="no_target_overwrite",
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

    hass.states.async_set(
        kitchen_physical_climate,
        HVACMode.HEAT_COOL,
        {
            **hass.states.get(kitchen_physical_climate).attributes,
            "temperature": 30,
            "current_temperature": 27,
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get(climate_id)
    assert state is not None
    assert state.attributes["target_temp_low"] == 19.0
    assert state.attributes["target_temp_high"] == 25.0
    assert state.attributes["current_temperature"] == 27
