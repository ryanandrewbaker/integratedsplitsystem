"""Shared fixtures for Integrated Split System M1 tests.

Expected integration contract (implemented by parent, not this package):
- ``const``: DOMAIN, DEFAULT_PROFILE_ID, CONF_* keys, SENSIBO_CONTROLLER_{AIR,SKY,UNKNOWN},
  optional ABORT_PHYSICAL_CLIMATE_IN_USE for duplicate config flow.
- ``async_setup_entry``: populate ``entry.runtime_data.coordinator`` (dataclass wrapper OK).
- Coordinator: ``boost_active`` bool; ``async_set_boost_active`` or ``set_boost_active``;
  ``profile_id`` (or ``connected_profile_id``) mirroring config entry profile link.
- Config flow: single user step (or final step) accepts FR-01 data keys; duplicate physical
  climate aborts with ``ABORT_PHYSICAL_CLIMATE_IN_USE``.
- ``async_setup_entry``: reject a second loaded entry bound to the same physical climate.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
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

pytest_plugins = ("pytest_homeassistant_custom_component",)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom integrations from ./custom_components for every test."""


def build_config_entry_data(
    *,
    physical_climate_entity_id: str,
    room_name: str,
    profile_id: str = DEFAULT_PROFILE_ID,
    sensibo_controller_type: str = SENSIBO_CONTROLLER_UNKNOWN,
    **extra: Any,
) -> dict[str, Any]:
    """Build config entry data matching the M1 contract (FR-01)."""
    return {
        CONF_PHYSICAL_CLIMATE_ENTITY_ID: physical_climate_entity_id,
        CONF_ROOM_NAME: room_name,
        CONF_PROFILE_ID: profile_id,
        CONF_SENSIBO_CONTROLLER_TYPE: sensibo_controller_type,
        **extra,
    }


async def register_mock_physical_climate(
    hass: HomeAssistant,
    entity_id: str,
    *,
    unique_id: str,
    platform: str = "sensibo",
    state: str = HVACMode.HEAT_COOL,
    attributes: dict[str, Any] | None = None,
) -> str:
    """Register a physical climate in the entity registry and set its state."""
    registry = er.async_get(hass)
    object_id = entity_id.split(".", 1)[1]
    registry.async_get_or_create(
        CLIMATE_DOMAIN,
        platform,
        unique_id,
        suggested_object_id=object_id,
    )
    base_attrs: dict[str, Any] = {
        ATTR_FRIENDLY_NAME: object_id.replace("_", " ").title(),
        "hvac_modes": [HVACMode.OFF, HVACMode.HEAT_COOL, HVACMode.COOL, HVACMode.FAN_ONLY],
        "fan_modes": ["auto", "low", "high", "strong"],
        "min_temp": 16,
        "max_temp": 30,
        "temperature": 22,
        "current_temperature": 22,
        "supported_features": 0,
    }
    if attributes:
        base_attrs.update(attributes)
    hass.states.async_set(entity_id, state, base_attrs)
    await hass.async_block_till_done()
    return entity_id


@pytest.fixture
async def physical_climate_factory(hass: HomeAssistant) -> Callable[..., Any]:
    """Factory for mock underlying climate entities."""

    async def _factory(
        entity_id: str,
        *,
        unique_id: str | None = None,
        platform: str = "sensibo",
        state: str = HVACMode.HEAT_COOL,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        return await register_mock_physical_climate(
            hass,
            entity_id,
            unique_id=unique_id or entity_id.replace(".", "_"),
            platform=platform,
            state=state,
            attributes=attributes,
        )

    return _factory


async def setup_config_entry(
    hass: HomeAssistant,
    data: dict[str, Any],
    *,
    entry_id: str | None = None,
    title: str | None = None,
) -> ConfigEntry:
    """Add a MockConfigEntry and run integration setup."""
    from custom_components.integrated_split_system import async_setup as domain_setup

    await domain_setup(hass, {})
    store = hass.data[DOMAIN]["profiles"]
    profile_id = data.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID)
    if profile_id != DEFAULT_PROFILE_ID and store.get_profile(profile_id) is None:
        await store.async_create_profile(
            profile_id, profile_id.replace("_", " ").title()
        )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        title=title or data[CONF_ROOM_NAME],
        entry_id=entry_id,
        version=1,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def get_runtime_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> Any:
    """Return the per-entry coordinator stored on config entry runtime_data."""
    loaded = hass.config_entries.async_get_entry(entry.entry_id)
    assert loaded is not None
    runtime = loaded.runtime_data
    assert runtime is not None, "integration must populate entry.runtime_data on setup"
    coordinator = getattr(runtime, "coordinator", None)
    assert coordinator is not None, "runtime_data must expose a .coordinator attribute"
    return coordinator


def climate_entities_for_entry(hass: HomeAssistant, entry_id: str) -> list[str]:
    """List integration-owned climate entity IDs for a config entry."""
    registry = er.async_get(hass)
    return sorted(
        entity.entity_id
        for entity in registry.entities.values()
        if entity.config_entry_id == entry_id and entity.domain == CLIMATE_DOMAIN
    )


async def async_set_boost_on_coordinator(coordinator: Any, active: bool) -> None:
    """Activate or clear boost on a coordinator without physical writes (EP-02)."""
    if hasattr(coordinator, "async_set_boost_active"):
        await coordinator.async_set_boost_active(active)
        return
    if hasattr(coordinator, "set_boost_active"):
        coordinator.set_boost_active(active)
        return
    pytest.fail(
        "Coordinator must implement async_set_boost_active or set_boost_active for EP-02"
    )


@contextmanager
def track_climate_service_calls(
    hass: HomeAssistant,
) -> Iterator[list[tuple[str, str, dict[str, Any]]]]:
    """Record homeassistant.services.async_call invocations for domain climate."""
    from homeassistant.core import ServiceRegistry

    calls: list[tuple[str, str, dict[str, Any]]] = []
    original = ServiceRegistry.async_call

    async def _tracked_async_call(
        self: ServiceRegistry,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        if domain == CLIMATE_DOMAIN:
            calls.append((domain, service, dict(service_data or {})))
        return await original(self, domain, service, service_data, **kwargs)

    with patch.object(ServiceRegistry, "async_call", _tracked_async_call):
        yield calls


@pytest.fixture
async def kitchen_physical_climate(
    physical_climate_factory: Callable[..., Any],
) -> str:
    """Kitchen mock physical climate (EP fixtures)."""
    return await physical_climate_factory(
        "climate.kitchen_ac",
        unique_id="sensibo_kitchen_ac",
        attributes={"device_type": "air"},
    )


@pytest.fixture
async def family_room_physical_climate(
    physical_climate_factory: Callable[..., Any],
) -> str:
    """Family room mock physical climate (EP fixtures)."""
    return await physical_climate_factory(
        "climate.family_room_ac",
        unique_id="sensibo_family_room_ac",
        attributes={"device_type": "sky"},
    )


@pytest.fixture
async def main_bedroom_physical_climate(
    physical_climate_factory: Callable[..., Any],
) -> str:
    """Main bedroom mock physical climate (shared-profile EP-02)."""
    return await physical_climate_factory(
        "climate.main_bedroom_ac",
        unique_id="sensibo_main_bedroom_ac",
    )
