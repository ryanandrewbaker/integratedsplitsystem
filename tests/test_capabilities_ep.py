"""EP-03 through EP-06 capability fixtures (M2 read-only)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.components.climate import HVACMode
from homeassistant.core import ServiceRegistry

from custom_components.integrated_split_system import async_setup as domain_setup
from custom_components.integrated_split_system.capabilities import (
    CapabilityCache,
    capabilities_from_physical_state,
    resolve_profile_fan_mode,
)
from custom_components.integrated_split_system.const import DOMAIN

from .conftest import (
    build_config_entry_data,
    climate_entities_for_entry,
    setup_config_entry,
    track_climate_service_calls,
)


def test_ep_03_profile_strong_allowed() -> None:
    profile = {"fan_stage_hints": {"high": "strong"}}
    mapped, diag = resolve_profile_fan_mode(profile, "high", ["auto", "strong", "low"])
    assert mapped == "strong"
    assert diag is None


def test_ep_04_profile_strong_not_permitted() -> None:
    profile = {"fan_stage_hints": {"high": "strong"}}
    mapped, diag = resolve_profile_fan_mode(profile, "high", ["auto", "low"])
    assert mapped is None
    assert diag == "profile_fan_not_supported"


async def test_ep_05_generic_non_sensibo_attrs_only_async(
    hass, physical_climate_factory
) -> None:
    physical = await physical_climate_factory(
        "climate.generic_ac",
        unique_id="generic_ac",
        platform="generic",
        attributes={
            "hvac_modes": [HVACMode.OFF, HVACMode.HEAT_COOL],
            "fan_modes": ["auto", "low"],
        },
    )
    cache = CapabilityCache(hass, physical)
    result = await cache.async_get()
    assert result.sensibo_enriched is False
    assert "auto" in result.fan_modes


async def test_ep_06_per_mode_fan_refresh(hass, physical_climate_factory) -> None:
    physical = await physical_climate_factory(
        "climate.sensibo_mode_ac",
        unique_id="sensibo_mode_ac",
        platform="sensibo",
        attributes={
            "hvac_modes": [HVACMode.COOL, HVACMode.HEAT_COOL],
            "fan_modes": ["auto"],
        },
    )
    cache = CapabilityCache(hass, physical)

    async def _capabilities_service(call: object) -> dict:
        return {"fan_modes": ["auto", "strong"]}

    hass.services.async_register(
        "sensibo", "get_device_capabilities", _capabilities_service
    )

    original = ServiceRegistry.async_call

    async def _fake_sensibo_call(
        self: ServiceRegistry,
        domain: str,
        service: str,
        service_data: dict | None = None,
        **kwargs: object,
    ) -> dict:
        if domain == "sensibo" and service == "get_device_capabilities":
            return {"fan_modes": ["auto", "strong"]}
        return await original(self, domain, service, service_data, **kwargs)

    with patch.object(ServiceRegistry, "async_call", _fake_sensibo_call):
        cool_caps = await cache.async_get(active_hvac_mode="cool", force_refresh=True)

    assert "strong" in cool_caps.fan_modes


async def test_ep_03_integration_proposed_fan_on_climate(
    hass, kitchen_physical_climate: str
) -> None:
    await domain_setup(hass, {})
    store = hass.data[DOMAIN]["profiles"]
    await store.async_create_profile(
        "kitchen_strong",
        "Kitchen strong",
    )
    profile = store.get_profile("kitchen_strong")
    assert profile is not None
    profile["fan_stage_hints"] = {"high": "strong"}

    entry = await setup_config_entry(
        hass,
        build_config_entry_data(
            physical_climate_entity_id=kitchen_physical_climate,
            room_name="Kitchen",
            profile_id="kitchen_strong",
        ),
        entry_id="ep03_integration",
    )
    climate_id = climate_entities_for_entry(hass, entry.entry_id)[0]
    with track_climate_service_calls(hass):
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": climate_id, "hvac_mode": HVACMode.HEAT_COOL},
            blocking=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get(climate_id)
    assert state is not None
    assert state.attributes.get("shadow_mode") is True
    assert "operating_state" in state.attributes
