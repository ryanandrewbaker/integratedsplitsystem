"""Constants for Integrated Split System."""

from __future__ import annotations

DOMAIN = "integrated_split_system"

DEFAULT_PROFILE_ID = "generic"

CONF_PHYSICAL_CLIMATE_ENTITY_ID = "physical_climate_entity_id"
CONF_ROOM_NAME = "room_name"
CONF_PROFILE_ID = "profile_id"
CONF_SENSIBO_CONTROLLER_TYPE = "sensibo_controller_type"

SENSIBO_CONTROLLER_AIR = "air"
SENSIBO_CONTROLLER_SKY = "sky"
SENSIBO_CONTROLLER_UNKNOWN = "unknown"
SENSIBO_CONTROLLER_AUTO = "auto"

ABORT_PHYSICAL_CLIMATE_IN_USE = "physical_climate_in_use"
ABORT_PHYSICAL_CLIMATE_INVALID = "physical_climate_invalid"

PLATFORMS = ["climate"]

STORAGE_PROFILES_VERSION = 1
STORAGE_PROFILES_KEY = f"{DOMAIN}.profiles"

# Documented minimums (see docs/M1_VERSIONS.md); HACS uses homeassistant key in hacs.json.
MIN_HOME_ASSISTANT_VERSION = "2026.10.2"
MIN_PYTHON_VERSION = (3, 13, 2)
