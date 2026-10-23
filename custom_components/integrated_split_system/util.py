"""Shared helpers."""

from __future__ import annotations

import math
import re
from typing import Any

from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import MINIMUM_TARGET_SEPARATION_C

_PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class TemperatureValidationError(ValueError):
    """Raised when a temperature value cannot be applied to the virtual band."""


def normalize_profile_id(name: str) -> str:
    """Derive a stable profile id slug from a display name."""
    slug = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        return "profile"
    if not slug[0].isalpha():
        slug = f"p_{slug}"
    return slug[:64]


def is_valid_profile_id(profile_id: str) -> bool:
    """Return True when profile_id is a safe stored identifier."""
    return bool(_PROFILE_ID_RE.match(profile_id))


def parse_finite_temperature(value: Any) -> float | None:
    """Return a finite float temperature or None when the value is not usable."""
    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "unknown", "unavailable", "none", "nan"}:
            return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def physical_state_temperature_unit(state: Any) -> str:
    """Infer the unit used by a physical climate state."""
    if state is None:
        return UnitOfTemperature.CELSIUS
    unit = state.attributes.get("temperature_unit")
    if unit in (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT):
        return unit
    uom = state.attributes.get("unit_of_measurement")
    if uom in (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT):
        return uom
    return UnitOfTemperature.CELSIUS


def convert_temperature_to_celsius(value: float, source_unit: str) -> float:
    """Convert a physical reading into the virtual entity's native Celsius."""
    if source_unit == UnitOfTemperature.CELSIUS:
        return value
    return TemperatureConverter.convert(
        value, source_unit, UnitOfTemperature.CELSIUS
    )


def parse_physical_temperature_celsius(state: Any, attribute: str) -> float | None:
    """Parse a physical climate attribute into Celsius when possible."""
    if state is None:
        return None
    raw = parse_finite_temperature(state.attributes.get(attribute))
    if raw is None:
        return None
    source_unit = physical_state_temperature_unit(state)
    return convert_temperature_to_celsius(raw, source_unit)


def round_to_temperature_step(value: float, step: float) -> float:
    """Round to the configured target step (e.g. 0.5 °C)."""
    if step <= 0:
        return value
    return round(value / step) * step


def apply_dual_setpoint_update(
    *,
    current_low: float,
    current_high: float,
    new_low: float | None = None,
    new_high: float | None = None,
    min_temp: float,
    max_temp: float,
    step: float,
    min_separation: float = MINIMUM_TARGET_SEPARATION_C,
) -> tuple[float, float]:
    """Apply a virtual dual-setpoint change, preserving the edited control when possible."""
    if new_low is None and new_high is None:
        raise TemperatureValidationError("no target provided")

    if new_low is not None:
        parsed_low = parse_finite_temperature(new_low)
        if parsed_low is None:
            raise TemperatureValidationError("invalid low temperature")
        new_low = round_to_temperature_step(parsed_low, step)

    if new_high is not None:
        parsed_high = parse_finite_temperature(new_high)
        if parsed_high is None:
            raise TemperatureValidationError("invalid high temperature")
        new_high = round_to_temperature_step(parsed_high, step)

    low = current_low
    high = current_high

    if new_low is not None and new_high is not None:
        low = float(new_low)
        high = float(new_high)
        if low > high:
            raise TemperatureValidationError("low higher than high")
        if high - low < min_separation:
            raise TemperatureValidationError("separation too small")
        low, high = _fit_band_to_limits(low, high, min_temp, max_temp, min_separation)
        return low, high

    if new_low is not None:
        low = float(new_low)
        if low < min_temp or low > max_temp:
            raise TemperatureValidationError("low out of range")
        high = current_high
        if high - low < min_separation:
            high = low + min_separation
        if high > max_temp:
            raise TemperatureValidationError("band exceeds max temperature")
        high = round_to_temperature_step(high, step)
        if high - low < min_separation:
            raise TemperatureValidationError("separation too small")
        return low, high

    # Only high changes.
    high = float(new_high)  # type: ignore[arg-type]
    if high < min_temp or high > max_temp:
        raise TemperatureValidationError("high out of range")
    low = current_low
    if high - low < min_separation:
        low = high - min_separation
    if low < min_temp:
        raise TemperatureValidationError("band below min temperature")
    low = round_to_temperature_step(low, step)
    if high - low < min_separation:
        raise TemperatureValidationError("separation too small")
    return low, high


def _fit_band_to_limits(
    low: float,
    high: float,
    min_temp: float,
    max_temp: float,
    min_separation: float,
) -> tuple[float, float]:
    """Clamp a band to device limits while keeping separation."""
    if low < min_temp or high > max_temp:
        raise TemperatureValidationError("target out of range")
    if high - low < min_separation:
        raise TemperatureValidationError("separation too small")
    return low, high


def clamp_temperature_band(
    low: float,
    high: float,
    *,
    min_separation: float = MINIMUM_TARGET_SEPARATION_C,
) -> tuple[float, float]:
    """Legacy helper for symmetric seeding; prefer apply_dual_setpoint_update."""
    low_f = float(low)
    high_f = float(high)
    if high_f < low_f:
        low_f, high_f = high_f, low_f
    if high_f - low_f < min_separation:
        high_f = low_f + min_separation
    return low_f, high_f
