"""Control temperature from configured sources (M2 read-only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_STALENESS_SECONDS, DEFAULT_STALENESS_SECONDS
from .util import parse_finite_temperature, parse_physical_temperature_celsius


@dataclass(slots=True)
class TemperatureSourceConfig:
    """One configured temperature input."""

    entity_id: str
    attribute: str | None = None


@dataclass(slots=True)
class SourceReading:
    """Diagnostic reading for one source."""

    entity_id: str
    attribute: str | None
    raw_value: Any
    value_celsius: float | None
    valid: bool
    stale: bool
    reason: str | None = None


@dataclass(slots=True)
class TemperatureSnapshot:
    """Aggregated control temperature result."""

    control_temperature_c: float | None
    method: str
    valid_source_count: int
    sources: list[SourceReading] = field(default_factory=list)
    degraded: bool = False


def parse_temperature_sources(raw: list[Any] | None) -> list[TemperatureSourceConfig]:
    """Parse config entry temperature source list."""
    if not raw:
        return []
    sources: list[TemperatureSourceConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entity_id = item.get("entity_id")
        if not entity_id:
            continue
        attr = item.get("attribute")
        sources.append(
            TemperatureSourceConfig(
                entity_id=str(entity_id),
                attribute=str(attr) if attr else None,
            )
        )
    return sources


class TemperatureInputManager:
    """Subscribe to sources and compute equal-weight average control temperature."""

    def __init__(
        self,
        hass: HomeAssistant,
        sources: list[TemperatureSourceConfig],
        *,
        staleness_seconds: int = DEFAULT_STALENESS_SECONDS,
        physical_fallback_entity_id: str | None = None,
    ) -> None:
        self._hass = hass
        self._sources = list(sources)
        self._staleness_seconds = staleness_seconds
        self._physical_fallback_entity_id = physical_fallback_entity_id
        self._unsub: list[Any] = []
        self._last_snapshot = TemperatureSnapshot(
            control_temperature_c=None, method="none", valid_source_count=0, degraded=True
        )

    @callback
    def async_setup_listeners(self, on_update: Any) -> None:
        """Track all source entities (and physical climate for attribute sources)."""
        entity_ids = {s.entity_id for s in self._sources}
        if not entity_ids and self._physical_fallback_entity_id:
            entity_ids.add(self._physical_fallback_entity_id)

        if not entity_ids:
            return

        @callback
        def _changed(_event: Any) -> None:
            self._last_snapshot = self._calculate()
            on_update()

        self._unsub.append(
            async_track_state_change_event(self._hass, sorted(entity_ids), _changed)
        )
        self._last_snapshot = self._calculate()

    def async_unload(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    @property
    def snapshot(self) -> TemperatureSnapshot:
        return self._last_snapshot

    def recalculate(self) -> TemperatureSnapshot:
        self._last_snapshot = self._calculate()
        return self._last_snapshot

    def _calculate(self) -> TemperatureSnapshot:
        configs = list(self._sources)
        if not configs and self._physical_fallback_entity_id:
            configs = [
                TemperatureSourceConfig(
                    self._physical_fallback_entity_id, "current_temperature"
                )
            ]

        readings: list[SourceReading] = []
        valid_values: list[float] = []
        now = datetime.now().astimezone()

        for src in configs:
            state = self._hass.states.get(src.entity_id)
            reading = self._read_source(state, src, now)
            readings.append(reading)
            if reading.valid and reading.value_celsius is not None:
                valid_values.append(reading.value_celsius)

        if not valid_values:
            return TemperatureSnapshot(
                control_temperature_c=None,
                method="unavailable",
                valid_source_count=0,
                sources=readings,
                degraded=True,
            )

        avg = sum(valid_values) / len(valid_values)
        method = "average" if len(valid_values) > 1 else "single"
        return TemperatureSnapshot(
            control_temperature_c=avg,
            method=method,
            valid_source_count=len(valid_values),
            sources=readings,
            degraded=False,
        )

    def _read_source(
        self, state: State | None, src: TemperatureSourceConfig, now: datetime
    ) -> SourceReading:
        if state is None or state.state in ("unavailable", "unknown"):
            return SourceReading(
                src.entity_id,
                src.attribute,
                None,
                None,
                False,
                False,
                "unavailable",
            )

        stale = self._is_stale(state, now)
        if stale:
            return SourceReading(
                src.entity_id,
                src.attribute,
                None,
                None,
                False,
                True,
                "stale",
            )

        if src.attribute:
            if src.attribute == "current_temperature" and state.domain == "climate":
                value_c = parse_physical_temperature_celsius(
                    self._hass, state, "current_temperature"
                )
            else:
                raw = state.attributes.get(src.attribute)
                value_c = self._attribute_to_celsius(state, raw)
        else:
            value_c = parse_finite_temperature(state.state)

        valid = value_c is not None
        raw_display = (
            state.attributes.get(src.attribute)
            if src.attribute
            else state.state
        )
        return SourceReading(
            src.entity_id,
            src.attribute,
            raw_display,
            value_c,
            valid,
            False,
            None if valid else "invalid",
        )

    def _attribute_to_celsius(self, state: State, raw: Any) -> float | None:
        parsed = parse_finite_temperature(raw)
        if parsed is None:
            return None
        from .util import convert_temperature_to_celsius, physical_state_temperature_unit

        unit = physical_state_temperature_unit(self._hass, state)
        return convert_temperature_to_celsius(parsed, unit)

    def _is_stale(self, state: State, now: datetime) -> bool:
        if state.last_updated is None:
            return False
        age = (now - state.last_updated).total_seconds()
        return age > self._staleness_seconds
