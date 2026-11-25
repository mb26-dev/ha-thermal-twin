"""Config and options flow for ThermalTwin."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_COMFORT_MAX,
    CONF_COMFORT_MIN,
    CONF_HUMIDITY_MAX,
    CONF_INDOOR_HUMIDITY,
    CONF_OUTDOOR_HUMIDITY,
    CONF_POWER_SENSOR,
    CONF_POWER_THRESHOLD,
    CONF_READY_BY,
    CONF_READY_TEMPERATURE,
    CONF_USE_SUN,
    CONF_WEATHER_ENTITY,
    DEFAULT_HUMIDITY_MAX,
    DEFAULT_POWER_THRESHOLD,
    CONF_HVAC_ENTITY,
    CONF_HVAC_TYPE,
    CONF_INDOOR_SENSOR,
    CONF_OUTDOOR_ENTITY,
    CONF_SOLAR_SENSOR,
    CONF_TARGET_TEMPERATURE,
    CONF_WINDOW_SENSORS,
    DEFAULT_TARGET_TEMPERATURE,
    DOMAIN,
    HVAC_TYPE_COOL,
    HVAC_TYPE_HEAT,
)

_TEMP_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=-10,
        max=45,
        step=0.5,
        unit_of_measurement="°C",
        mode=selector.NumberSelectorMode.BOX,
    )
)


def _options_schema() -> vol.Schema:
    """Schema shared by the config and the options flow."""
    return vol.Schema(
        {
            vol.Required(CONF_INDOOR_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class="temperature"
                )
            ),
            vol.Required(CONF_OUTDOOR_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "weather"])
            ),
            vol.Required(
                CONF_TARGET_TEMPERATURE, default=DEFAULT_TARGET_TEMPERATURE
            ): _TEMP_SELECTOR,
            vol.Optional(CONF_HVAC_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["climate", "switch", "binary_sensor", "input_boolean", "fan"]
                )
            ),
            vol.Required(CONF_HVAC_TYPE, default=HVAC_TYPE_HEAT): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[HVAC_TYPE_HEAT, HVAC_TYPE_COOL],
                    translation_key=CONF_HVAC_TYPE,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(CONF_WINDOW_SENSORS): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
            ),
            vol.Optional(CONF_SOLAR_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_COMFORT_MIN): _TEMP_SELECTOR,
            vol.Optional(CONF_COMFORT_MAX): _TEMP_SELECTOR,
            vol.Optional(CONF_INDOOR_HUMIDITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
            ),
            vol.Optional(CONF_OUTDOOR_HUMIDITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
            ),
            vol.Optional(CONF_HUMIDITY_MAX, default=DEFAULT_HUMIDITY_MAX): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=40,
                    max=90,
                    step=1,
                    unit_of_measurement="%",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_WEATHER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Optional(CONF_POWER_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional(
                CONF_POWER_THRESHOLD, default=DEFAULT_POWER_THRESHOLD
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=3000,
                    step=1,
                    unit_of_measurement="W",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_READY_BY): selector.TimeSelector(),
            vol.Optional(CONF_READY_TEMPERATURE): _TEMP_SELECTOR,
            vol.Optional(CONF_USE_SUN, default=True): selector.BooleanSelector(),
        }
    )


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if user_input[CONF_INDOOR_SENSOR] == user_input[CONF_OUTDOOR_ENTITY]:
        errors[CONF_OUTDOOR_ENTITY] = "same_entity"
    return errors


class ThermalTwinConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create one ThermalTwin per room."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                await self.async_set_unique_id(user_input[CONF_INDOOR_SENSOR])
                self._abort_if_unique_id_configured()
                name = user_input.pop(CONF_NAME)
                return self.async_create_entry(title=name, data={}, options=user_input)

        schema = vol.Schema({vol.Required(CONF_NAME): str}).extend(
            _options_schema().schema
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ThermalTwinOptionsFlow:
        """Return the options flow."""
        return ThermalTwinOptionsFlow()


class ThermalTwinOptionsFlow(OptionsFlow):
    """Change sensors and targets of a room."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                # Replace instead of merge so cleared optional fields are removed.
                return self.async_create_entry(data=user_input)

        schema = self.add_suggested_values_to_schema(
            _options_schema(), user_input or self.config_entry.options
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
