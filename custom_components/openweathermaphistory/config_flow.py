from __future__ import annotations

import logging
from datetime import datetime
from functools import partial
from typing import Any

import homeassistant.helpers.config_validation as cv
import jinja2
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    ATTR_0_SIG,
    ATTR_1_SIG,
    ATTR_2_SIG,
    ATTR_3_SIG,
    ATTR_4_SIG,
    ATTR_WATERTARGET,
    CONF_DATA,
    CONF_END_HOUR,
    CONF_FORMULA,
    CONF_LOOKBACK_DAYS,
    CONF_MAX_CALLS_PER_DAY,
    CONF_MAX_CALLS_PER_HOUR,
    CONF_START_HOUR,
    CONST_API_CALL,
    DFLT_LOOKBACK_DAYS,
    DFLT_MAX_CALLS_PER_DAY,
    DFLT_MAX_CALLS_PER_HOUR,
    DOMAIN_KEY,
    TYPE_BACKFILL_PCT,
    TYPE_CUSTOM,
    TYPE_DEFAULT_FACTOR,
    TYPE_TOTAL_RAIN,
)
from .data import RestData

_LOGGER: logging.Logger = logging.getLogger(__name__)

from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RESOURCES,
    CONF_SENSORS,
    CONF_TYPE,
)
from homeassistant.util.unit_system import METRIC_SYSTEM


class OpenweathermaphistoryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN_KEY):
    """Config flow to set up one location."""

    # The schema version of the entries that it creates
    # Home Assistant will call your migrate method if the version changes
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""

        self.config: dict[str, Any] = {}
        errors = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            name = user_input[CONF_NAME]
            api_key = user_input[CONF_API_KEY]

            # Only allow 1 instance per unique location
            await self.async_set_unique_id(f"{lat}_{lon}")
            self._abort_if_unique_id_configured()

            api_online = await _is_api_online(self.hass, api_key, lat, lon)
            if not api_online:
                errors["base"] = "Cannot connect, possible invalid_api_key"

            if not errors:
                self.config = {
                    CONF_LATITUDE: lat,
                    CONF_LONGITUDE: lon,
                    CONF_NAME: name,
                    CONF_API_KEY: api_key,
                }
                return await self.async_step_done()

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(
                    CONF_LATITUDE, default=self.hass.config.latitude
                ): cv.latitude,
                vol.Required(
                    CONF_LONGITUDE, default=self.hass.config.longitude
                ): cv.longitude,
                vol.Required(
                    CONF_NAME,
                    default=self.hass.config.location_name,
                ): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_done(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """User is done adding, setup the entry"""
        title = self.config[CONF_NAME]
        data = self.config
        data["platform"] = DOMAIN_KEY

        # Just add default sensor on initial setup, can edit in options flow later
        data[CONF_RESOURCES] = [
            {
                CONF_NAME: "rainfactor",
                CONF_TYPE: TYPE_DEFAULT_FACTOR,
                CONF_DATA: {
                    CONF_NAME: "rainfactor",
                    CONF_TYPE: TYPE_DEFAULT_FACTOR,
                    ATTR_0_SIG: 1,
                    ATTR_1_SIG: 0.5,
                    ATTR_2_SIG: 0.25,
                    ATTR_3_SIG: 0.12,
                    ATTR_4_SIG: 0.06,
                    ATTR_WATERTARGET: 10
                    if self.hass.config.units is METRIC_SYSTEM
                    else 0.4,
                },
            }
        ]
        data[CONF_LOOKBACK_DAYS] = DFLT_LOOKBACK_DAYS
        data[CONF_MAX_CALLS_PER_DAY] = DFLT_MAX_CALLS_PER_DAY
        data[CONF_MAX_CALLS_PER_HOUR] = DFLT_MAX_CALLS_PER_HOUR

        _LOGGER.info("Finished config flow: %s", data)
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OpenweathermaphistoryOptionsFlow:
        """Get the options flow for this handler."""
        return OpenweathermaphistoryOptionsFlow(config_entry)


class OpenweathermaphistoryOptionsFlow(config_entries.OptionsFlow):
    """Options flow for one location."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config = {}
        for k, v in config_entry.data.items():
            self.config[k] = v

        # options can overwrite original config data
        for k, v in config_entry.options.items():
            self.config[k] = v

        self.config[CONF_SENSORS] = {}
        for sensor in self.config.pop(CONF_RESOURCES, []):
            name = sensor[CONF_NAME]
            sensor.update(sensor.pop(CONF_DATA, {}))
            self.config[CONF_SENSORS][name] = sensor

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self.async_step_lookback_days()

    async def async_step_lookback_days(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handles config for lookback days and API limits"""

        if user_input is not None:
            self.config[CONF_LOOKBACK_DAYS] = user_input[CONF_LOOKBACK_DAYS]
            self.config[CONF_MAX_CALLS_PER_HOUR] = user_input[CONF_MAX_CALLS_PER_HOUR]
            self.config[CONF_MAX_CALLS_PER_DAY] = user_input[CONF_MAX_CALLS_PER_DAY]

            return await self.async_step_add_sensors()

        schema = vol.Schema(
            {
                vol.Required(CONF_LOOKBACK_DAYS, default=DFLT_LOOKBACK_DAYS): vol.All(
                    int, vol.Range(min=1, max=365)
                ),
                vol.Optional(
                    CONF_MAX_CALLS_PER_HOUR, default=DFLT_MAX_CALLS_PER_HOUR
                ): vol.All(int, vol.Range(min=0, max=600)),
                vol.Optional(
                    CONF_MAX_CALLS_PER_DAY, default=DFLT_MAX_CALLS_PER_DAY
                ): vol.All(int, vol.Range(min=0, max=10000)),
            }
        )

        return self.async_show_form(step_id="lookback_days", data_schema=schema)

    async def async_step_add_sensors(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        if CONF_SENSORS not in self.config:
            self.config[CONF_SENSORS] = {}

        sensor_names = list(self.config[CONF_SENSORS].keys())

        self.ensure_sensor_steps(sensor_names=sensor_names)

        options = {
            **{f"edit_{safe_name(name)}": f"Edit '{name}'" for name in sensor_names},
            "choose_sensor_type": "Add new sensor",
        }

        if len(sensor_names):
            options["remove_sensors"] = "Remove sensors"
            options["done"] = "Done"

        return self.async_show_menu(
            step_id="add_sensors",
            menu_options=options,
        )

    async def async_step_remove_sensors(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        if CONF_SENSORS not in self.config:
            self.config[CONF_SENSORS] = {}

        sensor_names = list(self.config[CONF_SENSORS].keys())

        self.ensure_sensor_steps(sensor_names=sensor_names)

        return self.async_show_menu(
            step_id="add_sensors",
            menu_options={
                **{
                    f"remove_{safe_name(name)}": f"Remove '{name}'"
                    for name in sensor_names
                },
                "add_sensors": "Back",
            },
        )

    def ensure_sensor_steps(self, sensor_names: list[str]):
        """Ensures we have a options flow step for each sensor already added.
        This allows the user to modify or delete already added sensors as part of the options flow.
        Adding methods this way is a workaround because HA doesn't allow us to pass any context data
        through the async_show_menu function into the next step."""
        for sensor_name in sensor_names:
            partial_edit = partial(self.partial_edit_sensor, sensor_name)
            edit_method = f"async_step_edit_{safe_name(sensor_name)}"
            setattr(self.__class__, edit_method, partial_edit)

            partial_remove = partial(self.partial_remove_sensor, sensor_name)
            remove_method = f"async_step_remove_{safe_name(sensor_name)}"
            setattr(self.__class__, remove_method, partial_remove)

    async def partial_remove_sensor(
        self, sensor_name: str, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove a sensor for a given sensor name"""
        if sensor_name in self.config[CONF_SENSORS]:
            del self.config[CONF_SENSORS][sensor_name]
        return await self.async_step_add_sensors()

    async def partial_edit_sensor(
        self, sensor_name: str, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit a sensor for a given sensor name"""

        # remove because it will get re-added after the edit is saved, potentially with a new name
        sensor = self.config[CONF_SENSORS].pop(sensor_name)
        sensor_type = sensor[CONF_TYPE]
        if sensor_type == TYPE_CUSTOM:
            return await self.async_step_add_custom_sensor(defaults=sensor)
        elif sensor_type == TYPE_TOTAL_RAIN:
            return await self.async_step_add_total_rain_sensor(defaults=sensor)
        elif sensor_type == TYPE_DEFAULT_FACTOR:
            return await self.async_step_add_rainfactor_sensor(defaults=sensor)
        elif sensor_type == TYPE_BACKFILL_PCT:
            return await self.async_step_add_backfill_sensor(defaults=sensor)

    async def async_step_choose_sensor_type(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Add a new sensor. Dispatcher selector to choose which type to add."""

        return self.async_show_menu(
            step_id="choose_sensor_type",
            menu_options={
                "add_total_rain_sensor": "Add total rain sensor",
                "add_rainfactor_sensor": "Add rainfactor sensor",
                "add_custom_sensor": "Add custom formula sensor",
                "add_backfill_sensor": "Add backfill pct sensor",
                "add_sensors": "Back",
            },
        )

    async def async_step_add_backfill_sensor(
        self,
        user_input: dict[str, Any] | None = None,
        defaults: dict[str, Any] | None = None,
    ) -> FlowResult:
        if user_input is not None:
            name = user_input[CONF_NAME]

            self.config[CONF_SENSORS][name] = {
                CONF_NAME: name,
                CONF_TYPE: TYPE_BACKFILL_PCT,
            }

            return await self.async_step_add_sensors()

        if defaults is None:
            defaults = {CONF_NAME: "backfill_pct"}

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)
                ): cv.string
            }
        )
        return self.async_show_form(step_id="add_backfill_sensor", data_schema=schema)

    async def async_step_add_total_rain_sensor(
        self,
        user_input: dict[str, Any] | None = None,
        defaults: dict[str, Any] | None = None,
    ) -> FlowResult:
        errors = {}

        if user_input is not None:
            name = user_input[CONF_NAME]
            start_hour = user_input[CONF_START_HOUR]
            end_hour = user_input[CONF_END_HOUR]

            self.config[CONF_SENSORS][name] = {
                CONF_START_HOUR: start_hour,
                CONF_END_HOUR: end_hour,
                CONF_NAME: name,
                CONF_TYPE: TYPE_TOTAL_RAIN,
            }

            if start_hour < end_hour:
                return await self.async_step_add_sensors()
            else:
                errors["hours"] = "Start hour must be before end hour."

        if defaults is None:
            defaults = {CONF_START_HOUR: -24, CONF_END_HOUR: 0}

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)
                ): cv.string,
                vol.Required(
                    CONF_START_HOUR,
                    default=defaults.get(CONF_START_HOUR, vol.UNDEFINED),
                ): vol.All(int, vol.Range(min=-999, max=0)),
                vol.Required(
                    CONF_END_HOUR, default=defaults.get(CONF_END_HOUR, vol.UNDEFINED)
                ): vol.All(int, vol.Range(min=-999, max=0)),
            }
        )

        return self.async_show_form(
            step_id="add_total_rain_sensor", data_schema=schema, errors=errors
        )

    async def async_step_add_rainfactor_sensor(
        self,
        user_input: dict[str, Any] | None = None,
        defaults: dict[str, Any] | None = None,
    ) -> FlowResult:
        if user_input is not None:
            name = user_input[CONF_NAME]
            self.config[CONF_SENSORS][name] = {
                CONF_NAME: name,
                CONF_TYPE: TYPE_DEFAULT_FACTOR,
                ATTR_0_SIG: user_input[ATTR_0_SIG],
                ATTR_1_SIG: user_input[ATTR_1_SIG],
                ATTR_2_SIG: user_input[ATTR_2_SIG],
                ATTR_3_SIG: user_input[ATTR_3_SIG],
                ATTR_4_SIG: user_input[ATTR_4_SIG],
                ATTR_WATERTARGET: user_input[ATTR_WATERTARGET],
            }
            return await self.async_step_add_sensors()

        if defaults is None:
            defaults = {
                ATTR_0_SIG: 1,
                ATTR_1_SIG: 0.5,
                ATTR_2_SIG: 0.25,
                ATTR_3_SIG: 0.12,
                ATTR_4_SIG: 0.06,
                ATTR_WATERTARGET: 10
                if self.hass.config.units is METRIC_SYSTEM
                else 0.4,
                CONF_NAME: "rainfactor",
            }

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)
                ): cv.string,
                vol.Required(
                    ATTR_0_SIG, default=defaults.get(ATTR_0_SIG, vol.UNDEFINED)
                ): cv.positive_float,
                vol.Required(
                    ATTR_1_SIG, default=defaults.get(ATTR_1_SIG, vol.UNDEFINED)
                ): cv.positive_float,
                vol.Required(
                    ATTR_2_SIG, default=defaults.get(ATTR_2_SIG, vol.UNDEFINED)
                ): cv.positive_float,
                vol.Required(
                    ATTR_3_SIG, default=defaults.get(ATTR_3_SIG, vol.UNDEFINED)
                ): cv.positive_float,
                vol.Required(
                    ATTR_4_SIG, default=defaults.get(ATTR_4_SIG, vol.UNDEFINED)
                ): cv.positive_float,
                vol.Required(
                    ATTR_WATERTARGET,
                    default=defaults.get(ATTR_WATERTARGET, vol.UNDEFINED),
                ): cv.positive_float,
            }
        )

        return self.async_show_form(step_id="add_rainfactor_sensor", data_schema=schema)

    async def async_step_add_custom_sensor(
        self,
        user_input: dict[str, Any] | None = None,
        defaults: dict[str, Any] | None = None,
    ) -> FlowResult:
        errors = {}

        if user_input is not None:
            name = user_input[CONF_NAME]
            formula = user_input[CONF_FORMULA]
            self.config[CONF_SENSORS][name] = {
                CONF_FORMULA: formula,
                CONF_TYPE: TYPE_CUSTOM,
                CONF_NAME: name,
            }

            if validate_formula(formula, self.config[CONF_LOOKBACK_DAYS]):
                return await self.async_step_add_sensors()
            else:
                errors["formula"] = "Invalid formula"

        if defaults is None:
            defaults = {}

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)
                ): cv.string,
                vol.Required(
                    CONF_FORMULA, default=defaults.get(CONF_FORMULA, vol.UNDEFINED)
                ): cv.string,
            }
        )

        return self.async_show_form(
            step_id="add_custom_sensor", data_schema=schema, errors=errors
        )

    async def async_step_done(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """User is done adding, setup the entry"""
        title = self.config[CONF_NAME]
        data = self.config
        data["platform"] = DOMAIN_KEY

        # transform data to match yaml format
        data[CONF_RESOURCES] = []
        for name, sensor in self.config.pop(CONF_SENSORS, {}).items():
            resource = {}
            resource[CONF_NAME] = name
            resource[CONF_TYPE] = sensor[CONF_TYPE]
            resource[CONF_DATA] = sensor
            data[CONF_RESOURCES].append(resource)

        _LOGGER.info("Finished config flow: %s", data)
        return self.async_create_entry(title=title, data=data)


async def _is_api_online(hass, api_key, lat, lon):
    if hass.config.units is METRIC_SYSTEM:
        units = "metric"
    else:
        units = "imperial"

    fmt_date = int(datetime.now().timestamp())
    rd = RestData()

    url = CONST_API_CALL % (lat, lon, fmt_date, api_key, units)
    await rd.set_resource(hass, url=url)
    await rd.async_update()
    return rd.data is not None


def safe_name(name: str) -> str:
    """Makes a safe function name by removing spaces and other weird characters"""
    return "".join([c if (c.isalpha() or c.isnumeric()) else "_" for c in name])


def validate_formula(formula: str, lookback_days: int) -> bool:
    allowed_vars: dict[str, Any] = {}

    for i in range(lookback_days):
        allowed_vars[f"day{i}rain"] = 0
        allowed_vars[f"day{i}snow"] = 0
        allowed_vars[f"day{i}humidity"] = 0
        allowed_vars[f"day{i}temp_high"] = 0
        allowed_vars[f"day{i}temp_low"] = 0
    allowed_vars["max"] = max
    allowed_vars["min"] = min
    allowed_vars["sum"] = sum

    environment = jinja2.Environment()
    template = environment.from_string("{{" + formula + "}}")
    try:
        float(template.render(allowed_vars))
        return True
    except Exception as e:
        _LOGGER.warn(
            "Could not evaluate custom formula in setup: %s. \n %s", formula, e
        )
        return False
