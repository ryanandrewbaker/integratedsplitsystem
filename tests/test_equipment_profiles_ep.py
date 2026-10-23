"""D02 EP-01 / EP-02 fixture criteria (M1)."""

from __future__ import annotations

from homeassistant.components.climate import SERVICE_SET_TEMPERATURE
from homeassistant.core import HomeAssistant

from custom_components.integrated_split_system.const import (
    CONF_PROFILE_ID,
    CONF_SENSIBO_CONTROLLER_TYPE,
    SENSIBO_CONTROLLER_AIR,
    SENSIBO_CONTROLLER_SKY,
)

from .conftest import (
    async_set_boost_on_coordinator,
    build_config_entry_data,
    climate_entities_for_entry,
    get_runtime_coordinator,
    setup_config_entry,
    track_climate_service_calls,
)


async def test_ep_01_independent_sensibo_types_and_profiles(
    hass: HomeAssistant,
    kitchen_physical_climate: str,
    family_room_physical_climate: str,
) -> None:
    """EP-01: Air+profile P and Sky+profile Q stored independently per entry."""
    profile_p = "profile_kitchen_dedicated"
    profile_q = "profile_family_sky"

    entry_air = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
            profile_id=profile_p,
            sensibo_controller_type=SENSIBO_CONTROLLER_AIR,
        ),
        entry_id="ep01_air",
    )
    entry_sky = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=family_room_physical_climate,
            room_name="Family Room",
            profile_id=profile_q,
            sensibo_controller_type=SENSIBO_CONTROLLER_SKY,
        ),
        entry_id="ep01_sky",
    )

    air_loaded = hass.config_entries.async_get_entry(entry_air.entry_id)
    sky_loaded = hass.config_entries.async_get_entry(entry_sky.entry_id)
    assert air_loaded is not None and sky_loaded is not None

    assert air_loaded.data[CONF_SENSIBO_CONTROLLER_TYPE] == SENSIBO_CONTROLLER_AIR
    assert sky_loaded.data[CONF_SENSIBO_CONTROLLER_TYPE] == SENSIBO_CONTROLLER_SKY
    assert air_loaded.data[CONF_PROFILE_ID] == profile_p
    assert sky_loaded.data[CONF_PROFILE_ID] == profile_q

    air_coordinator = get_runtime_coordinator(hass, entry_air)
    sky_coordinator = get_runtime_coordinator(hass, entry_sky)
    assert air_coordinator is not sky_coordinator

    air_profile = getattr(air_coordinator, "profile_id", None) or getattr(
        air_coordinator, "connected_profile_id", None
    )
    sky_profile = getattr(sky_coordinator, "profile_id", None) or getattr(
        sky_coordinator, "connected_profile_id", None
    )
    assert air_profile == profile_p
    assert sky_profile == profile_q


async def test_ep_02_shared_profile_independent_boost_and_setpoints(
    hass: HomeAssistant,
    family_room_physical_climate: str,
    main_bedroom_physical_climate: str,
) -> None:
    """EP-02: shared profile id; boost and setpoints on A do not change B."""
    shared_profile = "upstairs_shared"

    entry_a = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=family_room_physical_climate,
            room_name="Family Room",
            profile_id=shared_profile,
            sensibo_controller_type=SENSIBO_CONTROLLER_SKY,
        ),
        entry_id="ep02_a",
    )
    entry_b = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=main_bedroom_physical_climate,
            room_name="Main Bedroom",
            profile_id=shared_profile,
            sensibo_controller_type=SENSIBO_CONTROLLER_SKY,
        ),
        entry_id="ep02_b",
    )

    assert entry_a.data[CONF_PROFILE_ID] == shared_profile
    assert entry_b.data[CONF_PROFILE_ID] == shared_profile

    coordinator_a = get_runtime_coordinator(hass, entry_a)
    coordinator_b = get_runtime_coordinator(hass, entry_b)

    climate_a = climate_entities_for_entry(hass, entry_a.entry_id)[0]
    climate_b = climate_entities_for_entry(hass, entry_b.entry_id)[0]

    state_b_before = hass.states.get(climate_b)
    assert state_b_before is not None
    low_b_before = state_b_before.attributes.get("target_temp_low")
    high_b_before = state_b_before.attributes.get("target_temp_high")

    with track_climate_service_calls(hass) as climate_calls:
        await async_set_boost_on_coordinator(coordinator_a, True)
        await hass.async_block_till_done()

        await hass.services.async_call(
            "climate",
            SERVICE_SET_TEMPERATURE,
            {
                "entity_id": climate_a,
                "target_temp_low": 19.0,
                "target_temp_high": 25.0,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert coordinator_a.boost_active is True
    assert coordinator_b.boost_active is False

    state_b_after = hass.states.get(climate_b)
    assert state_b_after is not None
    assert state_b_after.attributes.get("target_temp_low") == low_b_before
    assert state_b_after.attributes.get("target_temp_high") == high_b_before

    physical_targets = {
        family_room_physical_climate,
        main_bedroom_physical_climate,
    }
    for _domain, _service, service_data in climate_calls:
        entity_id = service_data.get("entity_id")
        if isinstance(entity_id, list):
            assert not set(entity_id) & physical_targets
        elif entity_id:
            assert entity_id not in physical_targets
