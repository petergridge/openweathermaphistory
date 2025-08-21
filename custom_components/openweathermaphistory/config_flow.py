"""Config flow."""

from __future__ import annotations

import contextlib
import logging
import uuid

import jinja2
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RESOURCES,
)
from homeassistant.core import callback
from homeassistant.helpers import (
    config_validation as cv,
    entity_registry as er,
    selector as sel,
)
from homeassistant.util import location as location_util

from .const import (
    CONF_ATTRIBUTES,
    CONF_CREATE_SENSORS,
    CONF_FORMULA,
    CONF_INTIAL_DAYS,
    CONF_MAX_CALLS,
    CONF_MAX_DAYS,
    CONF_SENSORCLASS,
    CONF_STATECLASS,
    CONF_UID,
    CONST_PROXIMITY,
    DOMAIN,
    OPTIONS_BULK,
    OPTIONS_SENSOR_CLASS,
)
from .utils import validate_api_key

DEFAULT_NAME = "Home"
_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class WeatherHistoryFlowHandler(config_entries.ConfigFlow):
    """FLow handler."""

    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL
    VERSION = 2

    def __init__(self) -> None:  # noqa: D107
        self._errors = {}
        self._data = {}
        self.selected = {}

    async def async_step_user(self, user_input=None):
        """Initiate flow via the user interface."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(str(uuid.uuid4()))
            for data in self.hass.data.get(DOMAIN, {}).values():
                if (
                    location_util.distance(
                        user_input[CONF_LOCATION][CONF_LATITUDE],
                        user_input[CONF_LOCATION][CONF_LONGITUDE],
                        data[CONF_LOCATION][CONF_LATITUDE],
                        data[CONF_LOCATION][CONF_LONGITUDE],
                    )
                    < CONST_PROXIMITY
                ):
                    errors[CONF_LOCATION] = "close_proximity"
                if cv.slugify(user_input.get(CONF_NAME)) == cv.slugify(
                    data.get(CONF_NAME)
                ):
                    errors[CONF_NAME] = "duplicate_name"
                if errors:
                    break
            user_input[CONF_MAX_DAYS] = max(
                user_input[CONF_MAX_DAYS], user_input[CONF_INTIAL_DAYS]
            )

            errors, description_placeholders = await validate_api_key(
                user_input[CONF_API_KEY], "v3.0"
            )

            if not errors:
                # Input is valid, set data.
                self._data = {}
                resources = []
                self._data.update(user_input)
                resources.append(create_formula("daily_count", "none", "none",cv.slugify(
                    self._data.get(CONF_NAME)
                )))
                self._data[CONF_RESOURCES] = resources

                return await self.async_step_menu()

        if user_input is None:
            default_input = {}
        else:
            default_input = user_input

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=default_input.get(CONF_NAME, DEFAULT_NAME)
                ): cv.string,
                vol.Required(
                    CONF_API_KEY, default=default_input.get(CONF_API_KEY, "")
                ): cv.string,
                vol.Required(
                    CONF_LOCATION,
                    default=default_input.get(
                        CONF_LOCATION,
                        {
                            "latitude": self.hass.config.latitude,
                            "longitude": self.hass.config.longitude,
                        },
                    ),
                ): sel.LocationSelector(),
                vol.Required(
                    CONF_MAX_DAYS, default=default_input.get(CONF_MAX_DAYS, 5)
                ): sel.NumberSelector({"min": 1, "max": 30}),
                vol.Required(
                    CONF_INTIAL_DAYS, default=default_input.get(CONF_INTIAL_DAYS, 5)
                ): sel.NumberSelector({"min": 1, "max": 5}),
                vol.Required(
                    CONF_MAX_CALLS, default=default_input.get(CONF_MAX_CALLS, 500)
                ): sel.NumberSelector({"min": 500, "max": 5000, "step": 500}),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_bulk(self, user_input=None):
        """Invoke when a user initiates a flow via the user interface."""
        errors = {}
        newdata = {}
        newdata.update(self._data)
        if user_input is not None:
            if not errors:
                # Input is valid, set data.
                resources = []
                resources = self._data[CONF_RESOURCES]
                options = user_input.get(CONF_CREATE_SENSORS)
                # now process the create sensor options to build the required sensors
                resources = process_options(
                    self.hass,
                    self._data["name"],
                    options,
                    resources,
                    int(max(newdata[CONF_MAX_DAYS], newdata[CONF_INTIAL_DAYS])),
                )
                # update the configuation
                newdata[CONF_RESOURCES] = resources
                newdata[CONF_CREATE_SENSORS] = options
                self._data.update(newdata)
                # Return the form of the next step.
                return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CREATE_SENSORS, default=self._data.get(CONF_CREATE_SENSORS)
                ): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        translation_key=CONF_CREATE_SENSORS,
                        options=OPTIONS_BULK,
                        multiple=True,
                        mode="list",
                    )
                )
            }
        )
        return self.async_show_form(step_id="bulk", data_schema=schema, errors=errors)

    async def async_step_update(self, user_input=None):
        """Invoke when a user initiates a flow via the user interface."""
        errors = {}
        newdata = {}
        newdata.update(self._data)
        if user_input is not None:
            errors, description_placeholders = await validate_api_key(
                user_input[CONF_API_KEY], "v3.0"
            )

            user_input[CONF_MAX_DAYS] = max(
                user_input[CONF_MAX_DAYS], user_input[CONF_INTIAL_DAYS]
            )

            if not errors:
                newdata[CONF_NAME] = self._data.get(CONF_NAME)
                newdata[CONF_API_KEY] = user_input.get(CONF_API_KEY)
                newdata[CONF_LOCATION] = self._data.get(CONF_LOCATION)
                newdata[CONF_MAX_DAYS] = int(user_input.get(CONF_MAX_DAYS))
                newdata[CONF_INTIAL_DAYS] = int(user_input.get(CONF_INTIAL_DAYS))
                newdata[CONF_MAX_CALLS] = int(user_input.get(CONF_MAX_CALLS))
                # Return the form of the next step.
                self._data = newdata
                return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_API_KEY, default=self._data.get(CONF_API_KEY)
                ): cv.string,
                vol.Required(
                    CONF_MAX_DAYS, default=self._data.get(CONF_MAX_DAYS)
                ): sel.NumberSelector({"min": 1, "max": 30}),
                vol.Required(
                    CONF_INTIAL_DAYS, default=self._data.get(CONF_INTIAL_DAYS)
                ): sel.NumberSelector({"min": 1, "max": 30}),
                vol.Required(
                    CONF_MAX_CALLS, default=self._data.get(CONF_MAX_CALLS, 1000)
                ): sel.NumberSelector({"min": 500, "max": 5000, "step": 500}),
            }
        )
        return self.async_show_form(step_id="update", data_schema=schema, errors=errors)

    async def async_step_add(self, user_input=None):
        """Add a sensor."""
        errors = {}
        newdata = {}
        measurement = False
        string = False
        newdata.update(self._data)
        if user_input is not None:
            for sensor in self._data.get(CONF_RESOURCES):
                if cv.slugify(user_input.get(CONF_NAME)) == cv.slugify(
                    sensor.get(CONF_NAME)
                ):
                    errors[CONF_NAME] = "duplicate_name"
                    break
            if not self.hass.states.async_available(
                "sensor." + cv.slugify(user_input.get(CONF_NAME))
            ):
                errors[CONF_NAME] = "duplicate_name"
            evalform = evaluate_custom_formula(
                user_input.get(CONF_FORMULA), self._data.get(CONF_MAX_DAYS, 0)
            )
            match evalform:
                case "measurement":
                    measurement = True
                case "string":
                    string = True
                case "syntax":
                    errors[CONF_FORMULA] = "formula"
                case "undefined":
                    errors[CONF_FORMULA] = "formula_variable"

            if not errors:
                # Input is valid, set data.
                data = {}
                data[CONF_NAME] = user_input[CONF_NAME]
                data[CONF_FORMULA] = user_input[CONF_FORMULA]
                data[CONF_ATTRIBUTES] = user_input.get(CONF_ATTRIBUTES, None)
                data[CONF_SENSORCLASS] = user_input.get(CONF_SENSORCLASS, None)
                if measurement is True:
                    data[CONF_STATECLASS] = "measurement"
                if string is True:
                    data[CONF_SENSORCLASS] = "none"
                data[CONF_UID] = str(uuid.uuid4())
                newdata[CONF_RESOURCES].append(data)

                self._data = newdata
                return await self.async_step_menu()

        if user_input is None:
            default_input = {}
        else:
            default_input = user_input
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=default_input.get(CONF_NAME, "")
                ): cv.string,
                vol.Required(
                    CONF_FORMULA, default=default_input.get(CONF_FORMULA, "")
                ): sel.TemplateSelector({}),
                vol.Optional(
                    CONF_ATTRIBUTES, default=default_input.get(CONF_ATTRIBUTES, "")
                ): cv.string,
                vol.Required(
                    CONF_SENSORCLASS,
                    default=default_input.get(CONF_SENSORCLASS, "none"),
                ): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        translation_key="sensor_class", options=OPTIONS_SENSOR_CLASS
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="add",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_delete(self, user_input=None):
        """Delete."""
        errors = {}
        sensors = []
        newdata = {}
        newdata.update(self._data)

        if user_input is not None:
            if user_input == {}:
                # no data provided return to the menu
                return await self.async_step_menu()

            selected = int(user_input.get(CONF_NAME).split(".")[0])
            newdata[CONF_RESOURCES].pop(selected)
            self._data = newdata
            return await self.async_step_menu()
        # build the list
        for selection, sensor in enumerate(self._data.get(CONF_RESOURCES)):
            if sensor.get("enabled", None) is None:
                sensors.append(str(selection) + "." + sensor.get(CONF_NAME))
        list_schema = vol.Schema({vol.Optional(CONF_NAME): vol.In(sensors)})

        return self.async_show_form(
            step_id="delete", data_schema=list_schema, errors=errors
        )

    async def async_step_list_modify(self, user_input=None):
        """Update zone."""
        errors = {}
        items = []

        if user_input is not None:
            if user_input == {}:
                # no data provided return to the menu
                return await self.async_step_menu()
            # Return the form of the next step.
            self.selected = int(user_input.get(CONF_NAME).split(".")[0])
            return await self.async_step_modify()
        # build the list for display
        for selection, sensor in enumerate(self._data.get(CONF_RESOURCES)):
            if sensor.get("enabled", None) is None:
                items.append(str(selection) + "." + sensor.get(CONF_NAME))
        list_schema = vol.Schema({vol.Optional(CONF_NAME): vol.In(items)})

        return self.async_show_form(
            step_id="list_modify", data_schema=list_schema, errors=errors
        )

    async def async_step_modify(self, user_input=None):
        """Update zone."""
        errors = {}
        newdata = {}
        measurement = False
        string = False
        newdata.update(self._data)
        this_sensor = newdata.get(CONF_RESOURCES)[self.selected]

        if user_input is not None:
            evalform = evaluate_custom_formula(
                user_input.get(CONF_FORMULA), self._data.get(CONF_MAX_DAYS, 0)
            )
            match evalform:
                case "measurement":
                    measurement = True
                case "string":
                    string = True
                case "syntax":
                    errors[CONF_FORMULA] = "formula"
                case "undefined":
                    errors[CONF_FORMULA] = "formula_variable"

            if not errors:
                # Input is valid, set data.
                data = {}
                data[CONF_NAME] = this_sensor.get(CONF_NAME)
                data[CONF_FORMULA] = user_input[CONF_FORMULA]
                data[CONF_ATTRIBUTES] = user_input[CONF_ATTRIBUTES]
                data[CONF_SENSORCLASS] = user_input[CONF_SENSORCLASS]
                data[CONF_UID] = this_sensor[CONF_UID]
                if measurement is True:
                    data[CONF_STATECLASS] = "measurement"
                if string is True:
                    data[CONF_SENSORCLASS] = "none"
                newdata[CONF_RESOURCES][self.selected] = data
                self._data = newdata
                return await self.async_step_menu()

            this_sensor[CONF_FORMULA] = user_input[CONF_FORMULA]
            this_sensor[CONF_ATTRIBUTES] = user_input[CONF_ATTRIBUTES]
            this_sensor[CONF_SENSORCLASS] = user_input[CONF_SENSORCLASS]

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_FORMULA, default=this_sensor.get(CONF_FORMULA, None)
                ): sel.TemplateSelector({}),
                vol.Optional(
                    CONF_ATTRIBUTES, default=this_sensor.get(CONF_ATTRIBUTES, None)
                ): cv.string,
                vol.Required(
                    CONF_SENSORCLASS, default=this_sensor.get(CONF_SENSORCLASS, "none")
                ): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        translation_key="sensor_class", options=OPTIONS_SENSOR_CLASS
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="modify",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_menu(self, user_input=None):
        """Add a group or finalise the flow."""
        menu_options = ["bulk", "add"]
        if len(self._data.get(CONF_RESOURCES)) > 1:
            menu_options.extend(["list_modify", "delete"])
        menu_options.extend(["finalise"])
        return self.async_show_menu(step_id="menu", menu_options=menu_options)

    async def async_step_finalise(self, user_input=None):
        """Second step in config flow to add a repo to watch."""
        # User is done adding, create the config entry.
        return self.async_create_entry(title=self._data.get(CONF_NAME), data=self._data)

    # --- Options Flow ----------------------------------------------
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):  # noqa: D102
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Option flow."""

    VERSION = 2

    def __init__(self, config_entry) -> None:  # noqa: D107
        # self.config_entry = config_entry
        self._name = config_entry.data.get(CONF_NAME)
        self.selected = {}
        self._data = {}
        if config_entry.options == {}:
            self._data.update(config_entry.data)
        else:
            self._data.update(config_entry.options)

    async def async_step_user(self, user_input=None):
        """Work around from HA v23 11."""
        return

    async def async_step_init(self, user_input=None):
        """Initialise."""
        menu_options = ["update", "bulk", "add"]
        # only one sensor so don't show delete option
        if len(self._data.get(CONF_RESOURCES)) > 1:
            menu_options.extend(["list_modify", "delete"])
        menu_options.extend(["finalise"])
        return self.async_show_menu(
            step_id="user",
            menu_options=menu_options,
        )

    async def async_step_finalise(self, user_input=None):
        """Create the program config."""
        newdata = {}
        newdata.update(self._data)
        # the top level of the dictionary needs to change
        # for HA update to trigger, bug?
        if newdata.get("xx") == "x":
            newdata.update({"xx": "y"})
        else:
            newdata.update({"xx": "x"})
        # User is done adding, create the config entry.
        return self.async_create_entry(title=self._data.get(CONF_NAME), data=newdata)

    async def async_step_update(self, user_input=None):
        """Invoke when a user initiates a flow via the user interface."""
        errors = {}
        newdata = {}
        newdata.update(self._data)
        if user_input is not None:
            errors, description_placeholders = await validate_api_key(
                user_input[CONF_API_KEY], "v3.0"
            )

            user_input[CONF_MAX_DAYS] = max(
                user_input[CONF_MAX_DAYS], user_input[CONF_INTIAL_DAYS]
            )

            if not errors:
                newdata[CONF_NAME] = self._data.get(CONF_NAME)
                newdata[CONF_API_KEY] = user_input.get(CONF_API_KEY)
                newdata[CONF_LOCATION] = self._data.get(CONF_LOCATION)
                newdata[CONF_MAX_DAYS] = int(user_input.get(CONF_MAX_DAYS))
                newdata[CONF_INTIAL_DAYS] = int(user_input.get(CONF_INTIAL_DAYS))
                newdata[CONF_MAX_CALLS] = int(user_input.get(CONF_MAX_CALLS))
                # Input is valid, set data.
                resources = []
                resources = self._data[CONF_RESOURCES]
                options = newdata.get(CONF_CREATE_SENSORS)
                # now process the create sensor options to build the required sensors
                resources = process_options(
                    self.hass,
                    self._data["name"],
                    options,
                    resources,
                    int(max(user_input[CONF_MAX_DAYS], user_input[CONF_INTIAL_DAYS])),
                )
                # update the configuation
                newdata[CONF_RESOURCES] = resources
                newdata[CONF_CREATE_SENSORS] = options
                self._data.update(newdata)
                # Return the form of the next step.
                return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_API_KEY, default=self._data.get(CONF_API_KEY)
                ): cv.string,
                vol.Required(
                    CONF_MAX_DAYS, default=self._data.get(CONF_MAX_DAYS)
                ): sel.NumberSelector({"min": 1, "max": 30}),
                vol.Required(
                    CONF_INTIAL_DAYS, default=self._data.get(CONF_INTIAL_DAYS)
                ): sel.NumberSelector({"min": 1, "max": 30}),
                vol.Required(
                    CONF_MAX_CALLS, default=self._data.get(CONF_MAX_CALLS, 1000)
                ): sel.NumberSelector({"min": 500, "max": 5000, "step": 500}),
            }
        )
        return self.async_show_form(step_id="update", data_schema=schema, errors=errors)

    async def async_step_delete(self, user_input=None):
        """List for Delete."""
        errors = {}
        sensors = []
        newdata = {}
        newdata.update(self._data)
        if user_input is not None:
            if user_input == {}:
                # no data provided return to the menu
                return await self.async_step_init()

            selected = int(user_input.get(CONF_NAME).split(".")[0])
            sensorname = cv.slugify(user_input.get(CONF_NAME).split(".")[1])
            with contextlib.suppress(KeyError):
                # remove the sensor so it does not reapear as recovered
                er.async_get(self.hass).async_remove(f"sensor.{sensorname}".lower())

            newdata[CONF_RESOURCES].pop(selected)
            self._data = newdata
            return await self.async_step_init()
        # build the list
        for selection, sensor in enumerate(self._data.get(CONF_RESOURCES)):
            if sensor.get("enabled", None) is None:
                sensors.append(str(selection) + "." + sensor.get(CONF_NAME))
        list_schema = vol.Schema({vol.Optional(CONF_NAME): vol.In(sensors)})

        return self.async_show_form(
            step_id="delete", data_schema=list_schema, errors=errors
        )

    async def async_step_list_modify(self, user_input=None):
        """List Update zone."""
        errors = {}
        items = []

        if user_input is not None:
            if user_input == {}:
                # no data provided return to the menu
                return await self.async_step_init()
            # Return the form of the next step.
            self.selected = int(user_input.get(CONF_NAME).split(".")[0])

            return await self.async_step_modify()
        # build the list for display
        for selection, sensor in enumerate(self._data.get(CONF_RESOURCES)):
            if sensor.get("enabled", None) is None:
                items.append(str(selection) + "." + sensor.get(CONF_NAME))
        list_schema = vol.Schema({vol.Optional(CONF_NAME): vol.In(items)})

        return self.async_show_form(
            step_id="list_modify", data_schema=list_schema, errors=errors
        )

    async def async_step_modify(self, user_input=None):
        """Update zone."""
        errors = {}
        newdata = {}
        measurement = False
        string = False
        newdata.update(self._data)
        this_sensor = newdata.get(CONF_RESOURCES)[self.selected]

        if user_input is not None:
            evalform = evaluate_custom_formula(
                user_input.get(CONF_FORMULA), self._data.get(CONF_MAX_DAYS, 0)
            )
            match evalform:
                case "measurement":
                    measurement = True
                case "string":
                    string = True
                case "syntax":
                    errors[CONF_FORMULA] = "formula"
                case "undefined":
                    errors[CONF_FORMULA] = "formula_variable"

            if not errors:
                # Input is valid, set data.
                data = {}
                data[CONF_NAME] = this_sensor[CONF_NAME]
                data[CONF_FORMULA] = user_input[CONF_FORMULA]
                data[CONF_ATTRIBUTES] = user_input[CONF_ATTRIBUTES]
                data[CONF_SENSORCLASS] = user_input[CONF_SENSORCLASS]
                if measurement is True:
                    data[CONF_STATECLASS] = "measurement"
                if string is True:
                    data[CONF_SENSORCLASS] = "none"
                data[CONF_UID] = this_sensor[CONF_UID]
                newdata[CONF_RESOURCES][self.selected] = data
                self._data = newdata
                return await self.async_step_init()

            this_sensor[CONF_FORMULA] = user_input[CONF_FORMULA]
            this_sensor[CONF_ATTRIBUTES] = user_input[CONF_ATTRIBUTES]
            this_sensor[CONF_SENSORCLASS] = user_input[CONF_SENSORCLASS]

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_FORMULA,
                    default=this_sensor.get(
                        CONF_FORMULA, this_sensor.get(CONF_FORMULA)
                    ),
                ): sel.TemplateSelector({}),
                vol.Optional(
                    CONF_ATTRIBUTES,
                    default=this_sensor.get(
                        CONF_ATTRIBUTES, this_sensor.get(CONF_ATTRIBUTES, None)
                    ),
                ): cv.string,
                vol.Required(
                    CONF_SENSORCLASS, default=this_sensor.get(CONF_SENSORCLASS, "none")
                ): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        translation_key="sensor_class", options=OPTIONS_SENSOR_CLASS
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="modify",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_bulk(self, user_input=None):
        """Invoke when a user initiates a flow via the user interface."""
        errors = {}
        newdata = {}
        newdata.update(self._data)
        if user_input is not None:
            if not errors:
                # Input is valid, set data.
                resources = []
                resources = self._data[CONF_RESOURCES]
                options = user_input.get(CONF_CREATE_SENSORS)
                # now process the create sensor options to build the required sensors
                resources = process_options(
                    self.hass,
                    self._data["name"],
                    options,
                    resources,
                    int(max(newdata[CONF_MAX_DAYS], newdata[CONF_INTIAL_DAYS])),
                )
                # update the configuation
                newdata[CONF_RESOURCES] = resources
                newdata[CONF_CREATE_SENSORS] = options
                self._data.update(newdata)
                # Return the form of the next step.
                return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CREATE_SENSORS, default=self._data.get(CONF_CREATE_SENSORS)
                ): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        translation_key=CONF_CREATE_SENSORS,
                        options=OPTIONS_BULK,
                        multiple=True,
                        mode="list",
                    )
                )
            }
        )
        return self.async_show_form(step_id="bulk", data_schema=schema, errors=errors)

    async def async_step_add(self, user_input=None):
        """Add Sensor."""
        errors = {}
        newdata = {}
        measurement = False
        string = False
        newdata.update(self._data)
        if user_input is not None:
            for sensor in self._data.get(CONF_RESOURCES):
                if cv.slugify(user_input.get(CONF_NAME)) == cv.slugify(
                    sensor.get(CONF_NAME)
                ):
                    errors[CONF_NAME] = "duplicate_name"
                    break
            if not self.hass.states.async_available(
                "sensor." + cv.slugify(user_input.get(CONF_NAME))
            ):
                errors[CONF_NAME] = "duplicate_name"
            evalform = evaluate_custom_formula(
                user_input.get(CONF_FORMULA), self._data.get(CONF_MAX_DAYS, 0)
            )
            match evalform:
                case "measurement":
                    measurement = True
                case "string":
                    string = True
                case "syntax":
                    errors[CONF_FORMULA] = "formula"
                case "undefined":
                    errors[CONF_FORMULA] = "formula_variable"

            if not errors:
                # Input is valid, set data.
                data = {}
                data[CONF_NAME] = user_input[CONF_NAME]
                data[CONF_FORMULA] = user_input[CONF_FORMULA]
                data[CONF_ATTRIBUTES] = user_input.get(CONF_ATTRIBUTES, None)
                data[CONF_SENSORCLASS] = user_input.get(CONF_SENSORCLASS, None)
                if measurement is True:
                    data[CONF_STATECLASS] = "measurement"
                if string is True:
                    data[CONF_SENSORCLASS] = "none"
                data[CONF_UID] = str(uuid.uuid4())
                newdata[CONF_RESOURCES].append(data)

                self._data = newdata
                return await self.async_step_init()

        if user_input is None:
            default_input = {}
        else:
            default_input = user_input
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=default_input.get(CONF_NAME, "")
                ): cv.string,
                vol.Required(
                    CONF_FORMULA, default=default_input.get(CONF_FORMULA, "")
                ): sel.TemplateSelector({}),
                vol.Optional(
                    CONF_ATTRIBUTES, default=default_input.get(CONF_ATTRIBUTES, "")
                ): cv.string,
                vol.Required(
                    CONF_SENSORCLASS,
                    default=default_input.get(CONF_SENSORCLASS, "none"),
                ): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        translation_key="sensor_class", options=OPTIONS_SENSOR_CLASS
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="add",
            data_schema=schema,
            errors=errors,
        )


# ---- Helpers ----

def create_formula(sensor, sensorclass, stateclass, instance="Home"):
    """Create formula dictionary."""
    formula = {}
    formula[CONF_NAME] = "OWMH_" + instance + "_" + sensor
    formula[CONF_FORMULA] = "{{ " + sensor + " }}"
    formula[CONF_ATTRIBUTES] = ""
    formula[CONF_SENSORCLASS] = sensorclass
    formula[CONF_STATECLASS] = stateclass
    formula[CONF_UID] = str(uuid.uuid4())
    formula["enabled"] = True
    return formula

def add_to_list(list, item):
    """Check if the sensor exists before adding."""
    for i in list:
        if i.get("formula", None) == item.get("formula", None):
            # exits no need to add
            return list

    list.append(item)
    return list

def remove_from_list(hass, list, item):
    """Check if the sensor exists before deleting."""
    for n, i in enumerate(list):
        if i.get("formula", None) == item.get("formula", None):
            # found remove it and return the list
            with contextlib.suppress(KeyError):
                # remove the sensor so it does not reapear as recovered
                er.async_get(hass).async_remove(f"sensor.{i['name']}".lower())
            list.pop(n)
            return list
    return list


def process_options(hass, name ,options, resource_list, days):
    """Process the selected aut create options."""
    resources = resource_list
    if options:
        for i in range(6):
            if "forecast_rain" in options:
                resources = add_to_list(
                    resources,
                    create_formula(f"forecast{i}rain", "precipitation", "measurement",name),
                )
            else:
                resources = remove_from_list(
                    hass,
                    resources,
                    create_formula(f"forecast{i}rain", "precipitation", "measurement",name),
                )
            if "forecast_snow" in options:
                resources = add_to_list(
                    resources,
                    create_formula(f"forecast{i}snow", "precipitation", "measurement",name),
                )
            else:
                resources = remove_from_list(
                    hass,
                    resources,
                    create_formula(f"forecast{i}snow", "precipitation", "measurement",name),
                )
            if "forecast_max" in options:
                resources = add_to_list(
                    resources,
                    create_formula(f"forecast{i}max", "temperature", "measurement",name),
                )
            else:
                resources = remove_from_list(
                    hass,
                    resources,
                    create_formula(f"forecast{i}max", "precipitation", "measurement",name),
                )
            if "forecast_min" in options:
                resources = add_to_list(
                    resources,
                    create_formula(f"forecast{i}min", "temperature", "measurement",name),
                )
            else:
                resources = remove_from_list(
                    hass,
                    resources,
                    create_formula(f"forecast{i}min", "precipitation", "measurement",name),
                )
            if "forecast_humidity" in options:
                resources = add_to_list(
                    resources,
                    create_formula(f"forecast{i}humidity", "humidity", "measurement",name),
                )
            else:
                resources = remove_from_list(
                    hass,
                    resources,
                    create_formula(
                        f"forecast{i}humidity", "precipitation", "measurement",name
                    ),
                )
            if "forecast_pop" in options:
                resources = add_to_list(
                    resources, create_formula(f"forecast{i}pop", "none", "none",name)
                )
            else:
                resources = remove_from_list(
                    hass,
                    resources,
                    create_formula(f"forecast{i}pop", "precipitation", "measurement",name),
                )

        for i in range(days):
            if "hist_rain" in options:
                resources = add_to_list(
                    resources,
                    create_formula(f"day{i}rain", "precipitation", "measurement",name),
                )
            else:
                resources = remove_from_list(
                    hass,
                    resources,
                    create_formula(f"day{i}rain", "precipitation", "measurement",name),
                )
            if "hist_snow" in options:
                resources = add_to_list(
                    resources,
                    create_formula(f"day{i}snow", "precipitation", "measurement",name),
                )
            else:
                resources = remove_from_list(
                    hass,
                    resources,
                    create_formula(f"day{i}snow", "precipitation", "measurement",name),
                )
            if "hist_max" in options:
                add_to_list(
                    resources,
                    create_formula(f"day{i}max", "temperature", "measurement",name),
                )
            else:
                resources = remove_from_list(
                    hass,
                    resources,
                    create_formula(f"day{i}max", "precipitation", "measurement",name),
                )
            if "hist_min" in options:
                resources = add_to_list(
                    resources,
                    create_formula(f"day{i}min", "temperature", "measurement",name),
                )
            else:
                resources = remove_from_list(
                    hass,
                    resources,
                    create_formula(f"day{i}min", "precipitation", "measurement",name),
                )

        if "current_obs" in options:
            resources = add_to_list(
                resources,
                create_formula("current_rain", "precipitation", "measurement",name),
            )
            resources = add_to_list(
                resources,
                create_formula("current_snow", "precipitation", "measurement",name),
            )
            resources = add_to_list(
                resources, create_formula("current_humidity", "humidity", "measurement",name)
            )
            resources = add_to_list(
                resources, create_formula("current_temp", "temperature", "measurement",name)
            )
            resources = add_to_list(
                resources, create_formula("current_pressure", "pressure", "measurement",name)
            )
        else:
            resources = remove_from_list(
                hass,
                resources,
                create_formula("current_rain", "precipitation", "measurement",name),
            )
            resources = remove_from_list(
                hass,
                resources,
                create_formula("current_snow", "precipitation", "measurement",name),
            )
            resources = remove_from_list(
                hass,
                resources,
                create_formula("current_humidity", "humidity", "measurement",name),
            )
            resources = remove_from_list(
                hass,
                resources,
                create_formula("current_temp", "temperature", "measurement",name),
            )
            resources = remove_from_list(
                hass,
                resources,
                create_formula("current_pressure", "pressure", "measurement",name),
            )

    return resources


def evaluate_custom_formula(formula, max_days):
    """Evaluate the formula/template."""
    wvars = {}
    # default to initial days variable
    for i in range(int(max_days)):
        wvars[f"day{i}rain"] = 0
        wvars[f"day{i}snow"] = 0
        wvars[f"day{i}max"] = 0
        wvars[f"day{i}min"] = 0
    for i in range(int(max_days)):
        wvars[f"aggregate{i}date"] =  ""
        wvars[f"aggregate{i}precipitation"] = 0
        wvars[f"aggregate{i}max"] = 0
        wvars[f"aggregate{i}min"] = 0

    # forecast provides 7 days of data
    for i in range(6):
        wvars[f"forecast{i}pop"] = 0
        wvars[f"forecast{i}rain"] = 0
        wvars[f"forecast{i}snow"] = 0
        wvars[f"forecast{i}humidity"] = 0
        wvars[f"forecast{i}max"] = 0
        wvars[f"forecast{i}min"] = 0
    # current observations
    wvars["current_rain"] = 0
    wvars["current_snow"] = 0
    wvars["current_humidity"] = 0
    wvars["current_temp"] = 0
    wvars["current_pressure"] = 0
    wvars["remaining_backlog"] = 0
    wvars["daily_count"] = 0
    wvars["hourly_time"] = []
    wvars["hourly_rain"] = []

    environment = jinja2.Environment()
    template = environment.from_string(formula)

    # process the template and handle errors
    try:
        templatevalue = template.render(wvars)
        # if it sneaks through the evaluaton
        if templatevalue == "":
            raise jinja2.UndefinedError
    except jinja2.UndefinedError as err:
        _LOGGER.warning("Undefined variable in custom formula: %s \n %s", formula, err)
        return "undefined"
    except jinja2.TemplateSyntaxError as err:
        _LOGGER.warning(
            "Syntax error could not evaluate custom formula: %s \n %s", formula, err
        )
        return "syntax"

    try:
        templatevalue = float(templatevalue)

    except ValueError:
        # not a number
        return "string"
    else:
        return "measurement"
