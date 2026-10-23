"""Config entry field resolution (options override data)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_PROFILE_ID,
    CONF_SENSIBO_CONTROLLER_TYPE,
    DEFAULT_PROFILE_ID,
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
