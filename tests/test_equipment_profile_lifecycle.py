"""Equipment profile store lifecycle (M1)."""

from __future__ import annotations

from custom_components.integrated_split_system import async_setup as domain_setup
from custom_components.integrated_split_system.const import CONF_PROFILE_ID, DOMAIN

from .conftest import build_config_entry_data, setup_config_entry


async def test_cannot_delete_profile_referenced_by_entry(
    hass, kitchen_physical_climate: str
) -> None:
    profile_id = "in_use_profile"
    await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
            profile_id=profile_id,
        ),
        entry_id="profile_in_use",
    )
    await domain_setup(hass, {})
    store = hass.data[DOMAIN]["profiles"]
    assert profile_id in store.profiles_in_use(hass)
    assert await store.async_delete_profile(hass, profile_id) is False
    assert store.get_profile(profile_id) is not None


async def test_can_delete_unreferenced_profile(hass) -> None:
    await domain_setup(hass, {})
    store = hass.data[DOMAIN]["profiles"]
    await store.async_create_profile("orphan_profile", "Orphan")
    assert await store.async_delete_profile(hass, "orphan_profile") is True
    assert store.get_profile("orphan_profile") is None


async def test_profiles_in_use_honors_options_override(
    hass, kitchen_physical_climate: str
) -> None:
    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
            profile_id="data_profile",
        ),
        entry_id="profile_options_in_use",
    )
    hass.config_entries.async_update_entry(
        entry, options={CONF_PROFILE_ID: "options_profile"}
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert entry is not None
    await domain_setup(hass, {})
    store = hass.data[DOMAIN]["profiles"]
    await store.async_create_profile("options_profile", "From options")
    in_use = store.profiles_in_use(hass)
    assert "options_profile" in in_use
