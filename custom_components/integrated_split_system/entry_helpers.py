"""Config entry field resolution (options override data)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_PROFILE_ID,
    CONF_SENSIBO_CONTROLLER_TYPE,
    CONF_STALENESS_SECONDS,
    CONF_TEMPERATURE_SOURCES,
    DEFAULT_PROFILE_ID,
    DEFAULT_STALENESS_SECONDS,
    SENSIBO_CONTROLLER_UNKNOWN,
)


def get_config_value(entry: ConfigEntry, key: str, default: str | None = None) -> str | None:
    """Return options value when set, otherwise config entry data."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def get_profile_id(entry: ConfigEntry) -> str:
    """Effective connected equipment profile id for this room entry."""
    value = get_config_value(entry, CONF_PROFILE_ID, DEFAULT_PROFILE_ID)
    return value or DEFAULT_PROFILE_ID


def get_sensibo_controller_type(entry: ConfigEntry) -> str:
    """Effective Sensibo controller metadata for this room entry."""
    value = get_config_value(entry, CONF_SENSIBO_CONTROLLER_TYPE, SENSIBO_CONTROLLER_UNKNOWN)
    return value or SENSIBO_CONTROLLER_UNKNOWN


def get_temperature_sources_raw(entry: ConfigEntry) -> list[Any]:
    """Temperature source configuration list."""
    if CONF_TEMPERATURE_SOURCES in entry.options:
        raw = entry.options[CONF_TEMPERATURE_SOURCES]
    else:
        raw = entry.data.get(CONF_TEMPERATURE_SOURCES)
    return list(raw) if isinstance(raw, list) else []


def get_staleness_seconds(entry: ConfigEntry) -> int:
    """Max age for a temperature source reading."""
    raw = entry.options.get(CONF_STALENESS_SECONDS, entry.data.get(CONF_STALENESS_SECONDS))
    try:
        return int(raw) if raw is not None else DEFAULT_STALENESS_SECONDS
    except (TypeError, ValueError):
        return DEFAULT_STALENESS_SECONDS
