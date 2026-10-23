"""Read-only Sensibo controller identification from physical climate metadata."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, State

from .const import (
    SENSIBO_CONTROLLER_AIR,
    SENSIBO_CONTROLLER_SKY,
    SENSIBO_CONTROLLER_UNKNOWN,
)

_ATTR_DEVICE_TYPE = "device_type"


def controller_type_from_state(state: State | None) -> str:
    """Infer Sensibo Air/Sky from entity attributes when present."""
    if state is None:
        return SENSIBO_CONTROLLER_UNKNOWN
    raw = state.attributes.get(_ATTR_DEVICE_TYPE)
    if raw is None:
        return SENSIBO_CONTROLLER_UNKNOWN
    normalized = str(raw).strip().lower()
    if normalized == SENSIBO_CONTROLLER_AIR:
        return SENSIBO_CONTROLLER_AIR
    if normalized == SENSIBO_CONTROLLER_SKY:
        return SENSIBO_CONTROLLER_SKY
    return SENSIBO_CONTROLLER_UNKNOWN


def detect_controller_type(hass: HomeAssistant, entity_id: str) -> str:
    """Detect controller type from the physical climate entity state."""
    return controller_type_from_state(hass.states.get(entity_id))
