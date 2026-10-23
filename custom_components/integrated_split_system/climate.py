"""Virtual climate entities (M1: no physical actuator)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_PHYSICAL_CLIMATE_ENTITY_ID,
    CONF_PROFILE_ID,
    CONF_ROOM_NAME,
    CONF_SENSIBO_CONTROLLER_TYPE,
    DOMAIN,
)
from .coordinator import IntegratedSplitSystemCoordinator

_LOGGER = logging.getLogger(__name__)

DEFAULT_TARGET_LOW = 20.0
DEFAULT_TARGET_HIGH = 24.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate platform for one config entry."""
    runtime = entry.runtime_data
    assert runtime is not None
    async_add_entities([IntegratedSplitSystemClimate(hass, entry, runtime.coordinator)])


class IntegratedSplitSystemClimate(ClimateEntity):
    """Room virtual thermostat surface (two-target band); M1 is read-only toward physical."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_mode = HVACMode.HEAT_COOL
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL, HVACMode.COOL, HVACMode.FAN_ONLY]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    )

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: IntegratedSplitSystemCoordinator,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self.coordinator = coordinator
        self._physical_entity_id = entry.data[CONF_PHYSICAL_CLIMATE_ENTITY_ID]
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = self._build_device_info()
        self._target_temp_low = DEFAULT_TARGET_LOW
        self._target_temp_high = DEFAULT_TARGET_HIGH
        self._attr_fan_modes: list[str] | None = ["auto", "low", "high", "strong"]
        self._attr_fan_mode = "auto"
        self._sync_from_physical(hass.states.get(self._physical_entity_id))
        self._unsub_track: Any = None

    def _build_device_info(self) -> DeviceInfo:
        room = self._entry.data[CONF_ROOM_NAME]
        identifiers = {(DOMAIN, self._entry.entry_id)}
        via_device_id: str | None = None
        entity_registry = er.async_get(self.hass)
        physical = entity_registry.async_get(self._physical_entity_id)
        if physical and physical.device_id:
            via_device_id = physical.device_id
        return DeviceInfo(
            identifiers=identifiers,
            name=room,
            manufacturer="Integrated Split System",
            model="Virtual room climate",
            via_device_id=via_device_id,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to physical climate metadata updates (read-only)."""
        await super().async_added_to_hass()

        @callback
        def _physical_changed(event: Any) -> None:
            new_state = event.data.get("new_state")
            self._sync_from_physical(new_state)
            self.async_write_ha_state()

        self._unsub_track = async_track_state_change_event(
            self.hass, [self._physical_entity_id], _physical_changed
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from physical entity."""
        if self._unsub_track:
            self._unsub_track()
            self._unsub_track = None
        await super().async_will_remove_from_hass()

    def _sync_from_physical(self, state: Any) -> None:
        """Mirror advertised fan/HVAC options from physical entity when present."""
        if state is None:
            return
        fan_modes = state.attributes.get("fan_modes")
        if isinstance(fan_modes, list) and fan_modes:
            self._attr_fan_modes = list(fan_modes)
        hvac_modes = state.attributes.get("hvac_modes")
        if isinstance(hvac_modes, list) and hvac_modes:
            self._attr_hvac_modes = list(hvac_modes)
        current = state.attributes.get("current_temperature")
        if current is not None:
            self._attr_current_temperature = current
        temp = state.attributes.get("temperature")
        if temp is not None and self._target_temp_low == DEFAULT_TARGET_LOW:
            self._target_temp_low = max(float(temp) - 2.0, 16.0)
            self._target_temp_high = min(float(temp) + 2.0, 30.0)

    @property
    def target_temperature_low(self) -> float:
        return self._target_temp_low

    @property
    def target_temperature_high(self) -> float:
        return self._target_temp_high

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "physical_climate_entity_id": self._physical_entity_id,
            "profile_id": self._entry.data.get(CONF_PROFILE_ID),
            "sensibo_controller_type": self._entry.data.get(CONF_SENSIBO_CONTROLLER_TYPE),
            "boost_active": self.coordinator.boost_active,
            "target_temp_low": self._target_temp_low,
            "target_temp_high": self._target_temp_high,
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Update virtual band only (M1: never forwards to physical climate)."""
        if ATTR_TEMPERATURE in kwargs:
            temp = float(kwargs[ATTR_TEMPERATURE])
            self._target_temp_low = temp
            self._target_temp_high = temp
        if ATTR_TARGET_TEMP_LOW in kwargs:
            self._target_temp_low = float(kwargs[ATTR_TARGET_TEMP_LOW])
        if ATTR_TARGET_TEMP_HIGH in kwargs:
            self._target_temp_high = float(kwargs[ATTR_TARGET_TEMP_HIGH])
        self.async_write_ha_state()
