"""Options flow and option-backed runtime updates."""

from __future__ import annotations

from homeassistant.data_entry_flow import FlowResultType

from custom_components.integrated_split_system import async_setup as domain_setup
from custom_components.integrated_split_system.const import (
    CONF_PROFILE_ID,
    CONF_SENSIBO_CONTROLLER_TYPE,
    DEFAULT_PROFILE_ID,
    DOMAIN,
    SENSIBO_CONTROLLER_AIR,
    SENSIBO_CONTROLLER_SKY,
)

from .conftest import (
    build_config_entry_data,
    climate_entities_for_entry,
    get_runtime_coordinator,
    setup_config_entry,
)


async def test_options_flow_updates_profile_and_controller(
    hass,
    kitchen_physical_climate: str,
) -> None:
    """Options save reloads entry; coordinator and climate attributes reflect options."""
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
            profile_id=DEFAULT_PROFILE_ID,
            sensibo_controller_type=SENSIBO_CONTROLLER_AIR,
        ),
        entry_id="options_kitchen",
    )

    await domain_setup(hass, {})
    new_profile = "kitchen_options_profile"
    store = hass.data[DOMAIN]["profiles"]
    await store.async_create_profile(new_profile, "Kitchen options profile")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_PROFILE_ID: new_profile,
            CONF_SENSIBO_CONTROLLER_TYPE: SENSIBO_CONTROLLER_SKY,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    reloaded = hass.config_entries.async_get_entry(entry.entry_id)
    assert reloaded is not None
    assert reloaded.options[CONF_PROFILE_ID] == new_profile
    assert reloaded.options[CONF_SENSIBO_CONTROLLER_TYPE] == SENSIBO_CONTROLLER_SKY
    assert reloaded.data[CONF_PROFILE_ID] == DEFAULT_PROFILE_ID

    coordinator = get_runtime_coordinator(hass, reloaded)
    assert coordinator.profile_id == new_profile
    assert coordinator.sensibo_controller_type == SENSIBO_CONTROLLER_SKY

    climate_id = climate_entities_for_entry(hass, reloaded.entry_id)[0]
    state = hass.states.get(climate_id)
    assert state is not None
    assert state.attributes["profile_id"] == new_profile
    assert state.attributes["sensibo_controller_type"] == SENSIBO_CONTROLLER_SKY
