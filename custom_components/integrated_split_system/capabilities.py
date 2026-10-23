"""Read-only physical and Sensibo capability discovery (M2)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

SENSIBO_DOMAIN = "sensibo"
SENSIBO_GET_CAPABILITIES = "get_device_capabilities"


@dataclass(slots=True)
class ModeCapabilities:
    """Capabilities for one HVAC mode."""

    hvac_mode: str
    fan_modes: list[str] = field(default_factory=list)
    swing_modes: list[str] = field(default_factory=list)
    min_temp: float | None = None
    max_temp: float | None = None
    supported: bool = True
    source: str = "entity_attributes"


@dataclass(slots=True)
class DeviceCapabilities:
    """Merged capability snapshot for the physical climate."""

    hvac_modes: list[str] = field(default_factory=list)
    fan_modes: list[str] = field(default_factory=list)
    per_mode: dict[str, ModeCapabilities] = field(default_factory=dict)
    fan_only_supported: bool = False
    dry_supported: bool = False
    discovery_errors: list[str] = field(default_factory=list)
    sensibo_enriched: bool = False


def capabilities_from_physical_state(state: State | None) -> DeviceCapabilities:
    """Read generic climate capabilities from entity state attributes."""
    caps = DeviceCapabilities()
    if state is None:
        caps.discovery_errors.append("physical_unavailable")
        return caps

    hvac_modes = state.attributes.get("hvac_modes") or []
    caps.hvac_modes = [str(m) for m in hvac_modes]
    fan_modes = state.attributes.get("fan_modes") or []
    caps.fan_modes = [str(m) for m in fan_modes]

    caps.fan_only_supported = HVACMode.FAN_ONLY in caps.hvac_modes or "fan_only" in caps.hvac_modes
    caps.dry_supported = HVACMode.DRY in caps.hvac_modes or "dry" in caps.hvac_modes

    for mode in caps.hvac_modes:
        caps.per_mode[mode] = ModeCapabilities(
            hvac_mode=mode,
            fan_modes=list(caps.fan_modes),
            min_temp=_attr_float(state, "min_temp"),
            max_temp=_attr_float(state, "max_temp"),
            source="entity_attributes",
        )
    return caps


def _attr_float(state: State, key: str) -> float | None:
    raw = state.attributes.get(key)
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


class CapabilityCache:
    """Cache per-mode Sensibo capability lookups (M2 read-only)."""

    def __init__(self, hass: HomeAssistant, physical_entity_id: str) -> None:
        self._hass = hass
        self._physical_entity_id = physical_entity_id
        self._cache: dict[str, DeviceCapabilities] = {}
        self._sensibo_device_id: str | None = None

    async def async_get(
        self, *, active_hvac_mode: str | None = None, force_refresh: bool = False
    ) -> DeviceCapabilities:
        """Return capabilities; optionally refresh Sensibo enrichment for active mode."""
        state = self._hass.states.get(self._physical_entity_id)
        base = capabilities_from_physical_state(state)
        cache_key = active_hvac_mode or "__base__"
        if not force_refresh and cache_key in self._cache:
            return self._cache[cache_key]

        if await self._maybe_enrich_sensibo(base, state, active_hvac_mode):
            base.sensibo_enriched = True
        self._cache[cache_key] = base
        return base

    async def _maybe_enrich_sensibo(
        self,
        caps: DeviceCapabilities,
        state: State | None,
        active_hvac_mode: str | None,
    ) -> bool:
        if state is None:
            return False
        registry = er.async_get(self._hass)
        entry = registry.async_get(self._physical_entity_id)
        if not entry or entry.platform != SENSIBO_DOMAIN:
            return False
        if SENSIBO_GET_CAPABILITIES not in self._hass.services.async_services().get(
            SENSIBO_DOMAIN, {}
        ):
            return False

        device_id = await self._resolve_sensibo_device_id(entry)
        if not device_id:
            caps.discovery_errors.append("sensibo_device_id_missing")
            return False

        mode = active_hvac_mode or (caps.hvac_modes[0] if caps.hvac_modes else "cool")
        try:
            response = await self._hass.services.async_call(
                SENSIBO_DOMAIN,
                SENSIBO_GET_CAPABILITIES,
                {"device_id": device_id, "hvac_mode": mode},
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Sensibo capability discovery failed: %s", err)
            caps.discovery_errors.append("sensibo_capabilities_unavailable")
            return False

        if not isinstance(response, dict):
            return False

        fans = response.get("fan_modes") or response.get("fanModes") or []
        if isinstance(fans, list) and fans:
            fan_list = [str(f) for f in fans]
            caps.fan_modes = fan_list
            mode_caps = caps.per_mode.setdefault(
                mode,
                ModeCapabilities(hvac_mode=mode, source="sensibo"),
            )
            mode_caps.fan_modes = fan_list
            mode_caps.source = "sensibo"
        return True

    async def _resolve_sensibo_device_id(self, entity_entry: er.RegistryEntry) -> str | None:
        unique = entity_entry.unique_id
        if unique:
            return str(unique)
        return None


def resolve_profile_fan_mode(
    profile: dict[str, Any] | None,
    stage: str,
    permitted_fans: list[str],
) -> tuple[str | None, str | None]:
    """Map profile fan preference to a permitted physical fan mode (EP-03/EP-04)."""
    from .controller import map_selected_fan_to_sensibo

    if not permitted_fans:
        return None, "no_fan_modes"
    hints = (profile or {}).get("fan_stage_hints") or {}
    if stage in hints:
        preferred = str(hints[stage])
        normalized = {m.lower(): m for m in permitted_fans}
        exact = normalized.get(preferred.lower())
        if exact is None:
            return None, "profile_fan_not_supported"
        return exact, None
    mapped = map_selected_fan_to_sensibo(stage, permitted_fans)
    if not mapped:
        return None, "profile_fan_not_supported"
    return mapped, None
