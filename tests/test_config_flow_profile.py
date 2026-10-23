"""Config flow profile creation."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.integrated_split_system.const import (
    CONF_PHYSICAL_CLIMATE_ENTITY_ID,
    CONF_PROFILE_ID,
    CONF_ROOM_NAME,
    CONF_SENSIBO_CONTROLLER_TYPE,
    DEFAULT_PROFILE_ID,
    DOMAIN,
    PROFILE_CREATE_NEW,
    SENSIBO_CONTROLLER_UNKNOWN,
)


async def test_config_flow_create_profile_then_finish(hass, kitchen_physical_climate: str) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_ROOM_NAME: "Kitchen",
            CONF_PHYSICAL_CLIMATE_ENTITY_ID: kitchen_physical_climate,
            CONF_PROFILE_ID: PROFILE_CREATE_NEW,
            CONF_SENSIBO_CONTROLLER_TYPE: SENSIBO_CONTROLLER_UNKNOWN,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "profile"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"profile_name": "My Upstairs AC", "profile_id": "my_upstairs_ac"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PROFILE_ID] == "my_upstairs_ac"
    assert result["data"][CONF_PHYSICAL_CLIMATE_ENTITY_ID] == kitchen_physical_climate
