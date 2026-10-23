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
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    ATTR_SHADOW_MODE,
    CONF_PHYSICAL_CLIMATE_ENTITY_ID,
    CONF_ROOM_NAME,
    DOMAIN,
    MINIMUM_TARGET_SEPARATION_C,
    SHADOW_MODE_ENABLED,
)
from .coordinator import IntegratedSplitSystemCoordinator
from .entry_helpers import get_profile_id, get_sensibo_controller_type
from .util import (
    TemperatureValidationError,
    apply_dual_setpoint_update,
    parse_physical_temperature_celsius,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TARGET_LOW = 20.0
DEFAULT_TARGET_HIGH = 24.0

# M1 virtual surface: dual-band thermostat with explicit off; no fan or dry emulation yet.
M1_HVAC_MODES = [HVACMode.OFF, HVACMode.HEAT_COOL]


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
    _attr_hvac_mode = HVACMode.OFF
    _attr_hvac_modes = list(M1_HVAC_MODES)
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    _attr_min_temp = 16.0
    _attr_max_temp = 30.0
    _attr_target_temperature_step = 0.5

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
        self._targets_initialized = False
        self._apply_persisted_user_state()
        self._sync_readonly_from_physical(hass.states.get(self._physical_entity_id))
        self._unsub_track: Any = None

    def _apply_persisted_user_state(self) -> None:
        store = self.coordinator.room_store.data
        if store.get("user_configured"):
            if store.get("target_temp_low") is not None:
                self._target_temp_low = float(store["target_temp_low"])
            if store.get("target_temp_high") is not None:
                self._target_temp_high = float(store["target_temp_high"])
            self._targets_initialized = True
            self._attr_hvac_mode = store.get("hvac_mode", HVACMode.OFF)
        else:
            self._attr_hvac_mode = HVACMode.OFF

    def _build_device_info(self) -> DeviceInfo:
        room = self._entry.data[CONF_ROOM_NAME]
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=room,
            manufacturer="Integrated Split System",
            model="Virtual room climate",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to physical climate read-only telemetry."""
        await super().async_added_to_hass()

        @callback
        def _physical_changed(event: Any) -> None:
            new_state = event.data.get("new_state")
            try:
                self._sync_readonly_from_physical(new_state)
            except Exception:  # noqa: BLE001 — listener must never crash on bad telemetry
                _LOGGER.debug(
                    "Ignoring invalid physical telemetry from %s",
                    self._physical_entity_id,
                    exc_info=True,
                )
            self.async_write_ha_state()

        self._unsub_track = async_track_state_change_event(
            self.hass, [self._physical_entity_id], _physical_changed
        )
        self.coordinator.set_climate_update_callback(
            lambda: self.async_write_ha_state()
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from physical entity."""
        if self._unsub_track:
            self._unsub_track()
            self._unsub_track = None
        await super().async_will_remove_from_hass()

    def _sync_readonly_from_physical(self, state: Any) -> None:
        """Mirror read-only telemetry from physical entity; never copy its control surface."""
        if state is None or state.state in (None, "unavailable", "unknown"):
            return

        current = parse_physical_temperature_celsius(
            self.hass, state, "current_temperature"
        )
        if current is not None:
            self._attr_current_temperature = current

        min_temp = parse_physical_temperature_celsius(self.hass, state, "min_temp")
        if min_temp is not None:
            self._attr_min_temp = min_temp

        max_temp = parse_physical_temperature_celsius(self.hass, state, "max_temp")
        if max_temp is not None:
            self._attr_max_temp = max_temp

        if not self._targets_initialized and not self.coordinator.room_store.data.get(
            "user_configured"
        ):
            center = parse_physical_temperature_celsius(self.hass, state, "temperature")
            if center is not None:
                half = MINIMUM_TARGET_SEPARATION_C / 2
                try:
                    low, high = apply_dual_setpoint_update(
                        current_low=center - half,
                        current_high=center + half,
                        new_low=center - half,
                        new_high=center + half,
                        min_temp=self.min_temp,
                        max_temp=self.max_temp,
                        step=self.target_temperature_step or 0.5,
                    )
                except TemperatureValidationError:
                    return
                self._target_temp_low = low
                self._target_temp_high = high
                self._targets_initialized = True

    @property
    def target_temperature_low(self) -> float:
        return self._target_temp_low

    @property
    def target_temperature_high(self) -> float:
        return self._target_temp_high

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snap = (
            self.coordinator._temperature_manager.snapshot
            if self.coordinator._temperature_manager
            else None
        )
        output = self.coordinator.controller_output
        caps = self.coordinator.capabilities
        attrs: dict[str, Any] = {
            "physical_climate_entity_id": self._physical_entity_id,
            "profile_id": get_profile_id(self._entry),
            "sensibo_controller_type": get_sensibo_controller_type(self._entry),
            "boost_active": self.coordinator.boost_active,
            "minimum_target_separation_c": MINIMUM_TARGET_SEPARATION_C,
            ATTR_SHADOW_MODE: SHADOW_MODE_ENABLED,
        }
        if snap:
            attrs["control_temperature_c"] = snap.control_temperature_c
            attrs["temperature_source_method"] = snap.method
            attrs["temperature_sources_degraded"] = snap.degraded
            attrs["temperature_source_diagnostics"] = [
                {
                    "entity_id": r.entity_id,
                    "attribute": r.attribute,
                    "valid": r.valid,
                    "stale": r.stale,
                    "reason": r.reason,
                }
                for r in snap.sources
            ]
        if output:
            attrs["operating_state"] = output.desired_state
            attrs["operating_direction"] = output.desired_direction
            attrs["proposed_fan_stage"] = output.desired_fan_stage
            attrs["apply_automatic_fan_stage"] = output.apply_automatic_fan_stage
        attrs["proposed_fan_mode"] = self.coordinator.proposed_fan_mode
        attrs["fan_mapping_diagnostic"] = self.coordinator.fan_mapping_diagnostic
        if caps:
            attrs["physical_hvac_modes"] = caps.hvac_modes
            attrs["physical_fan_modes"] = caps.fan_modes
            attrs["fan_only_supported"] = caps.fan_only_supported
            attrs["dry_supported"] = caps.dry_supported
            attrs["capability_discovery_errors"] = caps.discovery_errors
        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Virtual HVAC mode only (M1: never forwards to physical climate)."""
        if hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_hvac_mode",
                translation_placeholders={"mode": str(hvac_mode)},
            )
        self._attr_hvac_mode = hvac_mode
        await self.coordinator.room_store.async_update(
            hvac_mode=hvac_mode,
            user_configured=True,
        )
        await self.coordinator.async_refresh_controller()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Update virtual comfort band only; enforce separation, limits, and step."""
        new_low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        new_high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        step = self.target_temperature_step or 0.5
        try:
            low, high = apply_dual_setpoint_update(
                current_low=self._target_temp_low,
                current_high=self._target_temp_high,
                new_low=new_low,
                new_high=new_high,
                min_temp=self.min_temp,
                max_temp=self.max_temp,
                step=step,
            )
        except TemperatureValidationError as err:
            key = "invalid_temperature"
            message = str(err)
            if "out of range" in message or "exceeds" in message or "below" in message:
                key = "temp_out_of_range"
            elif "separation" in message:
                key = "temp_separation_too_small"
            elif "low higher" in message:
                key = "low_temp_higher_than_high_temp"
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=key,
            ) from err

        self._target_temp_low = low
        self._target_temp_high = high
        self._targets_initialized = True
        await self.coordinator.room_store.async_update(
            target_temp_low=low,
            target_temp_high=high,
            user_configured=True,
        )
        await self.coordinator.async_refresh_controller()
        self.async_write_ha_state()
