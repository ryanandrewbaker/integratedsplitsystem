"""Config flow for Integrated Split System."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
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
    SENSIBO_CONTROLLER_AIR,
    SENSIBO_CONTROLLER_AUTO,
    SENSIBO_CONTROLLER_SKY,
    SENSIBO_CONTROLLER_UNKNOWN,
)
from .equipment_profile import EquipmentProfileStore
from .sensibo import detect_controller_type


def _profile_options(hass: HomeAssistant) -> list[SelectOptionDict]:
    store: EquipmentProfileStore = hass.data.get(DOMAIN, {}).get("profiles")  # type: ignore[assignment]
    options: list[SelectOptionDict] = [
        SelectOptionDict(value=DEFAULT_PROFILE_ID, label="Generic / default"),
    ]
    if store:
        for profile in store.list_profiles():
            if profile["id"] == DEFAULT_PROFILE_ID:
                continue
            options.append(
                SelectOptionDict(value=profile["id"], label=str(profile.get("name", profile["id"])))
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
                SelectSelectorConfig(options=_profile_options(hass), mode=SelectSelectorMode.DROPDOWN)
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

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> IntegratedSplitSystemOptionsFlow:
        """Return the options flow handler."""
        return IntegratedSplitSystemOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        await self._ensure_profiles_loaded()
        errors: dict[str, str] = {}

        if user_input is not None:
            physical = user_input[CONF_PHYSICAL_CLIMATE_ENTITY_ID]
            state = self.hass.states.get(physical)
            if state is None or state.domain != CLIMATE_DOMAIN:
                errors["base"] = "physical_climate_invalid"
            elif self._physical_bound_elsewhere(physical):
                return self.async_abort(reason=ABORT_PHYSICAL_CLIMATE_IN_USE)
            else:
                unique_id = self._physical_unique_id(physical)
                if unique_id:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                controller = user_input.get(
                    CONF_SENSIBO_CONTROLLER_TYPE, SENSIBO_CONTROLLER_AUTO
                )
                if controller == SENSIBO_CONTROLLER_AUTO:
                    controller = detect_controller_type(self.hass, physical)

                profile_id = user_input.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID)
                store: EquipmentProfileStore = self.hass.data[DOMAIN]["profiles"]
                if store.get_profile(profile_id) is None:
                    await store.async_create_profile(
                        profile_id, profile_id.replace("_", " ").title()
                    )

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

    async def _ensure_profiles_loaded(self) -> None:
        from . import async_setup as domain_setup

        await domain_setup(self.hass, {})

    def _physical_bound_elsewhere(self, physical: str) -> bool:
        for entry in self._async_current_entries():
            if entry.data.get(CONF_PHYSICAL_CLIMATE_ENTITY_ID) == physical:
                return True
        return False

    @staticmethod
    def _physical_unique_id(physical_entity_id: str) -> str | None:
        return f"physical:{physical_entity_id}"


class IntegratedSplitSystemOptionsFlow(config_entries.OptionsFlow):
    """Options flow for per-room settings."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage room options."""
        from . import async_setup as domain_setup

        await domain_setup(self.hass, {})

        if user_input is not None:
            profile_id = user_input.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID)
            store: EquipmentProfileStore = self.hass.data[DOMAIN]["profiles"]
            if store.get_profile(profile_id) is None:
                await store.async_create_profile(
                    profile_id, profile_id.replace("_", " ").title()
                )
            return self.async_create_entry(
                data={
                    CONF_PROFILE_ID: profile_id,
                    CONF_SENSIBO_CONTROLLER_TYPE: user_input[CONF_SENSIBO_CONTROLLER_TYPE],
                }
            )

        options = self.config_entry.options
        data = self.config_entry.data
        current_profile = options.get(CONF_PROFILE_ID, data.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID))
        current_controller = options.get(
            CONF_SENSIBO_CONTROLLER_TYPE,
            data.get(CONF_SENSIBO_CONTROLLER_TYPE, SENSIBO_CONTROLLER_UNKNOWN),
        )

        schema = vol.Schema(
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
        return self.async_show_form(step_id="init", data_schema=schema)
