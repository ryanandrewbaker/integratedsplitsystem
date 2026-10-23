"""Config flow for Integrated Split System."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    ABORT_PHYSICAL_CLIMATE_IN_USE,
    CONF_PHYSICAL_CLIMATE_ENTITY_ID,
    CONF_PROFILE_ID,
    CONF_ROOM_NAME,
    CONF_SENSIBO_CONTROLLER_TYPE,
    DEFAULT_PROFILE_ID,
    DOMAIN,
    PROFILE_CREATE_NEW,
    SENSIBO_CONTROLLER_AIR,
    SENSIBO_CONTROLLER_AUTO,
    SENSIBO_CONTROLLER_SKY,
    SENSIBO_CONTROLLER_UNKNOWN,
)
from .equipment_profile import EquipmentProfileStore
from .sensibo import detect_controller_type
from .util import is_valid_profile_id, normalize_profile_id


def _profile_options(hass: HomeAssistant, *, include_create: bool = True) -> list[SelectOptionDict]:
    store: EquipmentProfileStore = hass.data.get(DOMAIN, {}).get("profiles")  # type: ignore[assignment]
    options: list[SelectOptionDict] = [
        SelectOptionDict(value=DEFAULT_PROFILE_ID, label="Generic / default"),
    ]
    if store:
        for profile in sorted(store.list_profiles(), key=lambda p: str(p.get("name", p["id"]))):
            if profile["id"] == DEFAULT_PROFILE_ID:
                continue
            options.append(
                SelectOptionDict(
                    value=profile["id"],
                    label=str(profile.get("name", profile["id"])),
                )
            )
    if include_create:
        options.append(
            SelectOptionDict(value=PROFILE_CREATE_NEW, label="Create new profile…")
        )
    return options


def _user_schema(hass: HomeAssistant) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ROOM_NAME): TextSelector(),
            vol.Required(CONF_PHYSICAL_CLIMATE_ENTITY_ID): EntitySelector(
                EntitySelectorConfig(domain=CLIMATE_DOMAIN)
            ),
            vol.Optional(CONF_PROFILE_ID, default=DEFAULT_PROFILE_ID): SelectSelector(
                SelectSelectorConfig(
                    options=_profile_options(hass),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_SENSIBO_CONTROLLER_TYPE, default=SENSIBO_CONTROLLER_AUTO): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=SENSIBO_CONTROLLER_AUTO, label="Auto-detect"),
                        SelectOptionDict(value=SENSIBO_CONTROLLER_AIR, label="Sensibo Air"),
                        SelectOptionDict(value=SENSIBO_CONTROLLER_SKY, label="Sensibo Sky"),
                        SelectOptionDict(value=SENSIBO_CONTROLLER_UNKNOWN, label="Unknown"),
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


class IntegratedSplitSystemConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Integrated Split System."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending_user_input: dict[str, Any] | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> IntegratedSplitSystemOptionsFlow:
        """Return the options flow handler."""
        return IntegratedSplitSystemOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        await self._ensure_profiles_loaded()
        errors: dict[str, str] = {}

        if user_input is not None:
            profile_choice = user_input.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID)
            if profile_choice == PROFILE_CREATE_NEW:
                self._pending_user_input = dict(user_input)
                return await self.async_step_profile()

            physical = user_input[CONF_PHYSICAL_CLIMATE_ENTITY_ID]
            state = self.hass.states.get(physical)
            if state is None or state.domain != CLIMATE_DOMAIN:
                errors["base"] = "physical_climate_invalid"
            elif self._physical_bound_elsewhere(physical):
                return self.async_abort(reason=ABORT_PHYSICAL_CLIMATE_IN_USE)
            else:
                store: EquipmentProfileStore = self.hass.data[DOMAIN]["profiles"]
                profile_id = profile_choice
                if store.get_profile(profile_id) is None:
                    errors[CONF_PROFILE_ID] = "profile_invalid"
                else:
                    unique_id = self._config_entry_unique_id(physical)
                    if unique_id:
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                    controller = user_input.get(
                        CONF_SENSIBO_CONTROLLER_TYPE, SENSIBO_CONTROLLER_AUTO
                    )
                    if controller == SENSIBO_CONTROLLER_AUTO:
                        controller = detect_controller_type(self.hass, physical)

                    return self.async_create_entry(
                        title=user_input[CONF_ROOM_NAME],
                        data={
                            CONF_ROOM_NAME: user_input[CONF_ROOM_NAME],
                            CONF_PHYSICAL_CLIMATE_ENTITY_ID: physical,
                            CONF_PROFILE_ID: profile_id,
                            CONF_SENSIBO_CONTROLLER_TYPE: controller,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(self.hass),
            errors=errors,
        )

    async def async_step_profile(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Create a new shared equipment profile."""
        await self._ensure_profiles_loaded()
        errors: dict[str, str] = {}
        store: EquipmentProfileStore = self.hass.data[DOMAIN]["profiles"]

        if user_input is not None:
            display_name = user_input["profile_name"].strip()
            profile_id = user_input.get("profile_id") or normalize_profile_id(display_name)
            profile_id = normalize_profile_id(str(profile_id))
            if not display_name:
                errors["profile_name"] = "required"
            elif not is_valid_profile_id(profile_id):
                errors["profile_id"] = "invalid"
            elif store.get_profile(profile_id) is not None:
                errors["profile_id"] = "already_exists"
            else:
                await store.async_create_profile(profile_id, display_name)
                pending = dict(self._pending_user_input or {})
                pending[CONF_PROFILE_ID] = profile_id
                self._pending_user_input = None
                return await self.async_step_user(pending)

        schema = vol.Schema(
            {
                vol.Required("profile_name"): TextSelector(),
                vol.Optional("profile_id"): TextSelector(),
            }
        )
        return self.async_show_form(step_id="profile", data_schema=schema, errors=errors)

    async def _ensure_profiles_loaded(self) -> None:
        from . import async_setup as domain_setup

        await domain_setup(self.hass, {})

    def _physical_bound_elsewhere(self, physical: str) -> bool:
        for entry in self._async_current_entries():
            if entry.data.get(CONF_PHYSICAL_CLIMATE_ENTITY_ID) == physical:
                return True
        return False

    def _config_entry_unique_id(self, physical_entity_id: str) -> str | None:
        """Prefer entity-registry unique id; fall back to entity id (see docs/M1_ENTITY_IDENTITY.md)."""
        registry = er.async_get(self.hass)
        entity = registry.async_get(physical_entity_id)
        if entity and entity.unique_id:
            return f"{entity.platform}.{entity.unique_id}"
        return f"entity_id:{physical_entity_id}"


class IntegratedSplitSystemOptionsFlow(config_entries.OptionsFlowWithReload):
    """Options flow for per-room settings (auto-reloads entry on save)."""

    def __init__(self) -> None:
        self._pending_options: dict[str, Any] | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage room options."""
        from . import async_setup as domain_setup

        await domain_setup(self.hass, {})

        if user_input is not None:
            profile_choice = user_input.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID)
            if profile_choice == PROFILE_CREATE_NEW:
                self._pending_options = dict(user_input)
                return await self.async_step_profile()

            store: EquipmentProfileStore = self.hass.data[DOMAIN]["profiles"]
            if store.get_profile(profile_choice) is None:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._options_schema(),
                    errors={CONF_PROFILE_ID: "profile_invalid"},
                )
            return self.async_create_entry(
                data={
                    CONF_PROFILE_ID: profile_choice,
                    CONF_SENSIBO_CONTROLLER_TYPE: user_input[CONF_SENSIBO_CONTROLLER_TYPE],
                }
            )

        return self.async_show_form(step_id="init", data_schema=self._options_schema())

    async def async_step_profile(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Create a profile from options flow."""
        from . import async_setup as domain_setup

        await domain_setup(self.hass, {})
        errors: dict[str, str] = {}
        store: EquipmentProfileStore = self.hass.data[DOMAIN]["profiles"]

        if user_input is not None:
            display_name = user_input["profile_name"].strip()
            profile_id = normalize_profile_id(
                str(user_input.get("profile_id") or display_name)
            )
            if not display_name:
                errors["profile_name"] = "required"
            elif not is_valid_profile_id(profile_id):
                errors["profile_id"] = "invalid"
            elif store.get_profile(profile_id) is not None:
                errors["profile_id"] = "already_exists"
            else:
                await store.async_create_profile(profile_id, display_name)
                pending = dict(self._pending_options or {})
                self._pending_options = None
                controller = pending.get(
                    CONF_SENSIBO_CONTROLLER_TYPE,
                    get_current_controller(self.config_entry),
                )
                return self.async_create_entry(
                    data={
                        CONF_PROFILE_ID: profile_id,
                        CONF_SENSIBO_CONTROLLER_TYPE: controller,
                    }
                )

        schema = vol.Schema(
            {
                vol.Required("profile_name"): TextSelector(),
                vol.Optional("profile_id"): TextSelector(),
            }
        )
        return self.async_show_form(step_id="profile", data_schema=schema, errors=errors)

    def _options_schema(self) -> vol.Schema:
        entry = self.config_entry
        current_profile = entry.options.get(
            CONF_PROFILE_ID, entry.data.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID)
        )
        current_controller = get_current_controller(entry)
        return vol.Schema(
            {
                vol.Optional(CONF_PROFILE_ID, default=current_profile): SelectSelector(
                    SelectSelectorConfig(
                        options=_profile_options(self.hass),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_SENSIBO_CONTROLLER_TYPE, default=current_controller): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=SENSIBO_CONTROLLER_AIR, label="Sensibo Air"),
                            SelectOptionDict(value=SENSIBO_CONTROLLER_SKY, label="Sensibo Sky"),
                            SelectOptionDict(value=SENSIBO_CONTROLLER_UNKNOWN, label="Unknown"),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )


def get_current_controller(entry: config_entries.ConfigEntry) -> str:
    return entry.options.get(
        CONF_SENSIBO_CONTROLLER_TYPE,
        entry.data.get(CONF_SENSIBO_CONTROLLER_TYPE, SENSIBO_CONTROLLER_UNKNOWN),
    )
