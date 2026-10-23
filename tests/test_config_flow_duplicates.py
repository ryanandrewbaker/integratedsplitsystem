"""FR-01: duplicate physical climate binding must abort config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.integrated_split_system.const import (
    CONF_PHYSICAL_CLIMATE_ENTITY_ID,
    CONF_PROFILE_ID,
    CONF_ROOM_NAME,
    CONF_SENSIBO_CONTROLLER_TYPE,
    DEFAULT_PROFILE_ID,
    DOMAIN,
    SENSIBO_CONTROLLER_UNKNOWN,
)

from .conftest import build_config_entry_data, setup_config_entry

try:
    from custom_components.integrated_split_system.const import (
        ABORT_PHYSICAL_CLIMATE_IN_USE,
    )
except ImportError:
    ABORT_PHYSICAL_CLIMATE_IN_USE = "physical_climate_in_use"


async def test_duplicate_physical_climate_rejected_in_config_flow(
    hass: HomeAssistant,
    kitchen_physical_climate: str,
) -> None:
    """Second config flow for the same physical entity aborts without replacing entry."""
    existing = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="existing_kitchen",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_PHYSICAL_CLIMATE_ENTITY_ID: kitchen_physical_climate,
            CONF_ROOM_NAME: "Kitchen duplicate",
            CONF_PROFILE_ID: DEFAULT_PROFILE_ID,
            CONF_SENSIBO_CONTROLLER_TYPE: SENSIBO_CONTROLLER_UNKNOWN,
        },
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == ABORT_PHYSICAL_CLIMATE_IN_USE

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].entry_id == existing.entry_id


async def test_duplicate_physical_climate_rejected_on_direct_setup(
    hass: HomeAssistant,
    kitchen_physical_climate: str,
) -> None:
    """A second MockConfigEntry with the same physical climate must not load."""
    await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
        ),
        entry_id="first_binding",
    )

    duplicate = MockConfigEntry(
        domain=DOMAIN,
        title="Kitchen duplicate",
        data=build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen duplicate",
        ),
        entry_id="duplicate_binding",
        version=1,
    )
    duplicate.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(duplicate.entry_id)
    await hass.async_block_till_done()

    loaded = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    assert len(loaded) == 1
    assert loaded[0].entry_id == "first_binding"
