"""Constants for Integrated Split System."""

from __future__ import annotations

DOMAIN = "integrated_split_system"

DEFAULT_PROFILE_ID = "generic"

CONF_PHYSICAL_CLIMATE_ENTITY_ID = "physical_climate_entity_id"
CONF_ROOM_NAME = "room_name"
CONF_PROFILE_ID = "profile_id"
CONF_SENSIBO_CONTROLLER_TYPE = "sensibo_controller_type"
CONF_TEMPERATURE_SOURCES = "temperature_sources"
CONF_STALENESS_SECONDS = "staleness_seconds"

DEFAULT_STALENESS_SECONDS = 600

# Temperature source entry: {"entity_id": str, "attribute": str | null}
# attribute null/omitted => entity state value

SENSIBO_CONTROLLER_AIR = "air"
SENSIBO_CONTROLLER_SKY = "sky"
SENSIBO_CONTROLLER_UNKNOWN = "unknown"
SENSIBO_CONTROLLER_AUTO = "auto"

ABORT_PHYSICAL_CLIMATE_IN_USE = "physical_climate_in_use"
ABORT_PHYSICAL_CLIMATE_INVALID = "physical_climate_invalid"

PROFILE_CREATE_NEW = "__create_new__"

MINIMUM_TARGET_SEPARATION_C = 2.0

PLATFORMS = ["climate"]

STORAGE_PROFILES_VERSION = 1
STORAGE_PROFILES_KEY = f"{DOMAIN}.profiles"
STORAGE_ROOM_STATE_VERSION = 1
STORAGE_ROOM_STATE_KEY = f"{DOMAIN}.room_state"

ATTR_SHADOW_MODE = "shadow_mode"
SHADOW_MODE_ENABLED = True

# Documented minimums (see docs/M1_VERSIONS.md); HACS uses homeassistant key in hacs.json.
MIN_HOME_ASSISTANT_VERSION = "2026.10.2"
MIN_PYTHON_VERSION = (3, 14, 2)
