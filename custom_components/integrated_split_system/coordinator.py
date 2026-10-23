"""Per-room runtime coordinator (M2 read-only controller)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .capabilities import CapabilityCache, DeviceCapabilities, resolve_profile_fan_mode
from .const import CONF_PHYSICAL_CLIMATE_ENTITY_ID, DEFAULT_PROFILE_ID, DOMAIN
from .controller import (
    ControllerState,
    Direction,
    StateMachineInput,
    StateMachineOutput,
    compute_kitchen_climate_controller,
)
from .entry_helpers import (
    get_profile_id,
    get_sensibo_controller_type,
    get_staleness_seconds,
    get_temperature_sources_raw,
)
from .equipment_profile import EquipmentProfileStore
from .room_store import RoomStateStore
from .temperature import TemperatureInputManager, parse_temperature_sources


class IntegratedSplitSystemCoordinator:
    """Holds per-entry runtime state, temperature inputs, and controller output."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.boost_active = False
        self.profile_id = DEFAULT_PROFILE_ID
        self.sensibo_controller_type = "unknown"
        self.room_store = RoomStateStore(hass, entry.entry_id)
        physical = entry.data[CONF_PHYSICAL_CLIMATE_ENTITY_ID]
        self._capability_cache = CapabilityCache(hass, physical)
        self._temperature_manager: TemperatureInputManager | None = None
        self.controller_output: StateMachineOutput | None = None
        self.capabilities: DeviceCapabilities | None = None
        self.proposed_fan_mode: str | None = None
        self.fan_mapping_diagnostic: str | None = None
        self._climate_callback: Any = None

    async def async_setup(self) -> None:
        """Load persistence and subscribe to temperature sources."""
        await self.room_store.async_load()
        self.refresh_from_entry(self.entry)
        sources = parse_temperature_sources(get_temperature_sources_raw(self.entry))
        physical = self.entry.data[CONF_PHYSICAL_CLIMATE_ENTITY_ID]
        self._temperature_manager = TemperatureInputManager(
            self.hass,
            sources,
            staleness_seconds=get_staleness_seconds(self.entry),
            physical_fallback_entity_id=physical,
        )
        self._temperature_manager.async_setup_listeners(self._on_temperature_changed)
        await self.async_refresh_controller()

    def async_unload(self) -> None:
        if self._temperature_manager:
            self._temperature_manager.async_unload()

    def set_climate_update_callback(self, callback: Any) -> None:
        self._climate_callback = callback

    @callback
    def _on_temperature_changed(self) -> None:
        self.hass.async_create_task(self.async_refresh_controller())

    def refresh_from_entry(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self.profile_id = get_profile_id(entry)
        self.sensibo_controller_type = get_sensibo_controller_type(entry)

    async def async_set_boost_active(self, active: bool) -> None:
        """Record boost state only (M2: no physical writes)."""
        self.boost_active = active
        await self.async_refresh_controller()

    def set_boost_active(self, active: bool) -> None:
        self.boost_active = active

    async def async_refresh_controller(self) -> None:
        """Recompute read-only controller output and capabilities."""
        store = self.room_store.data
        hvac_mode = store.get("hvac_mode", HVACMode.OFF)
        climate_on = hvac_mode != HVACMode.OFF
        virtual_fan_only = hvac_mode == HVACMode.FAN_ONLY

        temp_mgr = self._temperature_manager
        snapshot = temp_mgr.recalculate() if temp_mgr else None
        control_temp = snapshot.control_temperature_c if snapshot else None

        self.capabilities = await self._capability_cache.async_get(
            active_hvac_mode=str(hvac_mode) if climate_on else None
        )

        current_state = ControllerState(store.get("controller_state", ControllerState.IDLE))
        current_direction = Direction(store.get("controller_direction", Direction.HEAT))

        output = compute_kitchen_climate_controller(
            StateMachineInput(
                climate_on=climate_on,
                virtual_fan_only=virtual_fan_only,
                temperature=control_temp,
                base_low=float(store.get("target_temp_low") or 20.0),
                base_high=float(store.get("target_temp_high") or 24.0),
                manual_boost=self.boost_active,
                heat_demand_active=False,
                cool_demand_active=False,
                fan_automatic=True,
                current_state=current_state,
                current_direction=current_direction,
            )
        )
        self.controller_output = output

        await self._update_fan_proposal(output, str(hvac_mode))

        store["controller_state"] = output.desired_state
        store["controller_direction"] = output.desired_direction
        await self.room_store.async_update(
            controller_state=output.desired_state,
            controller_direction=output.desired_direction,
        )

        if self._climate_callback:
            self._climate_callback()

    async def _update_fan_proposal(
        self, output: StateMachineOutput, hvac_mode: str
    ) -> None:
        self.proposed_fan_mode = None
        self.fan_mapping_diagnostic = None
        if not output.apply_automatic_fan_stage:
            return
        caps = self.capabilities
        if not caps:
            return
        mode_caps = caps.per_mode.get(hvac_mode)
        permitted = mode_caps.fan_modes if mode_caps else caps.fan_modes
        profiles: EquipmentProfileStore | None = self.hass.data.get(DOMAIN, {}).get("profiles")
        profile = profiles.get_profile(self.profile_id) if profiles else None
        mapped, diag = resolve_profile_fan_mode(
            profile, output.desired_fan_stage, permitted
        )
        self.proposed_fan_mode = mapped
        self.fan_mapping_diagnostic = diag
