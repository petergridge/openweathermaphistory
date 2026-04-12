"""Platform for historical rain factor Sensor integration."""

from __future__ import annotations

from datetime import timedelta
import logging

import jinja2

from homeassistant.components.persistent_notification import async_create, async_dismiss
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_RESOURCES,
    EVENT_HOMEASSISTANT_STARTED,
    MATCH_ALL,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    ATTRIBUTION,
    CONF_ATTRIBUTES,
    CONF_FORMULA,
    CONF_INTIAL_DAYS,
    CONF_MAX_DAYS,
    CONF_PRECISION,
    CONF_SENSORCLASS,
    CONF_STATECLASS,
    CONF_UID,
    CONST_INITIAL,
    DOMAIN,
)
from .weatherhistory import Weather

SCAN_INTERVAL = timedelta(minutes=5)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry. form config flow."""

    if config_entry.options != {}:
        config = config_entry.options
    else:
        config = config_entry.data

    weather = Weather(hass, config)
    # initialise the weather data
    weather.set_processing_type(CONST_INITIAL)
    await weather.async_update()

    sensors = []
    coordinator = WeatherCoordinator(hass, weather)
    # append multiple sensors using the single weather class
    for resource in config[CONF_RESOURCES]:
        if resource.get("enabled", True):
            sensor = WeatherHistory(hass, config, resource, weather, coordinator)
            sensors.append(sensor)

    async_add_entities(sensors)

    async def handle_event(event_data):
        if event_data.data.get("entry") == config_entry.data.get("name"):
            if event_data.data.get("action") == "list_variables":
                sensors[0].list_vars()
            if event_data.data.get("action") == "api_call":
                await sensors[0].api_call(event_data.data.get("api"))

    # Listen for when event is fired
    hass.bus.async_listen("owmh_event", handle_event)

    done = hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STARTED, await let_weather_know_hass_has_started(weather)
    )
    done()
    return True


async def let_weather_know_hass_has_started(weather):
    """Let the coordinator know HA is loaded so backloading can commence."""
    weather.set_processing_type("general")


class WeatherCoordinator(DataUpdateCoordinator):
    """Weather API data coordinator. Refresh the data independantly of the sensor."""

    def __init__(self, hass: HomeAssistant, weather) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

        self._weather = weather

    async def _async_update_data(self):
        _LOGGER.error(1)
        """Fetch data from API endpoint."""
        # process n records every cycle
        await self._weather.async_update()


class WeatherHistory(CoordinatorEntity, SensorEntity):
    """Rain factor class defn."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_attribution = ATTRIBUTION
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(  # noqa: D107
        self,
        hass: HomeAssistant,
        config,
        resource,
        weather: Weather,
        coordinator: CoordinatorEntity,
    ) -> None:
        # subscribe to the API data coordinator
        super().__init__(coordinator)

        self._hass = hass
        self._state = 0
        self._weather = weather
        self._extra_attributes = None
        self._name = resource[CONF_NAME]
        self._formula = resource[CONF_FORMULA]
        self._attributes = resource.get(CONF_ATTRIBUTES)
        self._initdays = config.get(CONF_INTIAL_DAYS)
        self._maxdays = config.get(CONF_MAX_DAYS)
        self._sensor_class = resource.get(CONF_SENSORCLASS, None)
        self._state_class = resource.get(CONF_STATECLASS, None)
        self._precision = resource.get(CONF_PRECISION, None)
        self._uuid = resource.get(CONF_UID)
        self._hidden_by = resource.get("hidden_by")


    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.determine_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Add to Hass."""
        self._hass.async_create_task(self.async_update1())
        await super().async_added_to_hass()

    async def api_call(self, api):
        """Call API."""
        await self._weather.show_call_data(api)

    async def async_update1(self):
        """Update the sensor."""
        self.determine_state()
        self.async_write_ha_state()


    async def async_update(self):
        """Update the sensor."""
        #return
        self.determine_state()
        self.async_write_ha_state()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def suggested_display_precision(self):
        """Return the precision of the sensor."""
        return self._precision

    @property
    def unique_id(self):
        """Return a unique_id for this entity."""
        return self._uuid

    @property
    def state_class(self) -> SensorStateClass:
        """Handle string instances."""
        match self._state_class:
            case "measurement":
                return SensorStateClass.MEASUREMENT
            case "measurement_angle":
                return SensorStateClass.MEASUREMENT_ANGLE

    @property
    def native_unit_of_measurement(self):
        """Set Unit."""
        match self._sensor_class:
            case "humidity":
                return "%"
            case "precipitation":
               return "mm"
            case "precipitation_intensity":
                return "mm/h"
            case "temperature":
                return "°C"
            case "pressure":
                return "hPa"
            case "wind_direction":
                return "°"
            case "wind_speed":
                return "m/s"

    @property
    def device_class(self) -> SensorDeviceClass:
        """Handle string instances."""
        match self._sensor_class:
            case "humidity":
                return SensorDeviceClass.HUMIDITY
            case "precipitation":
                return SensorDeviceClass.PRECIPITATION
            case "precipitation_intensity":
                return SensorDeviceClass.PRECIPITATION_INTENSITY
            case "temperature":
                return SensorDeviceClass.TEMPERATURE
            case "pressure":
                return SensorDeviceClass.PRESSURE

    @property
    def native_value(self):
        """Return the state."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._extra_attributes

    def determine_state(self):
        """Determine the sensor state."""

        try:
            self._state = float(
                self._evaluate_custom_formula(
                    self._formula, self._update_vars(self._weather)
                )
            )
        except ValueError:
            self._state = self._evaluate_custom_formula(
                self._formula, self._update_vars(self._weather)
            )
        # return the attributes if requested
        if self._attributes is not None:
            self._extra_attributes = self._evaluate_custom_attr(
                self._attributes, self._update_vars(self._weather)
            )

    def _evaluate_custom_formula(self, formula: str, wvars: dict):
        """Evaluate the formula/template."""
        environment = jinja2.Environment()
        template = environment.from_string(formula)
        # process the template and handle errors
        try:
            return template.render(wvars)
        except jinja2.UndefinedError as err:
            _LOGGER.warning(
                "Variable not defined in custom formula: %s \n %s", formula, err
            )
            return 0
        except jinja2.TemplateSyntaxError as err:
            _LOGGER.warning(
                "Syntax error could not evaluate custom formula: %s \n %s", formula, err
            )
            return 0

    def _evaluate_custom_attr(self, attributes: list, wvars: dict):
        """Take the list of vars and build the attrs dictionaty."""
        attrs = {}
        attrs_list = (
            attributes.replace(" ", "").replace("'", "").strip("[]'").split(",")
        )
        for item in attrs_list:
            if item in wvars:
                attrs.update({item: wvars[item]})
        return attrs

    def _update_vars(self, weather: Weather):
        wvars = {}
        # default to initial days variable
        # need to define 'dummy' versions in the config flow as well
        for i in range(int(max(weather.max_days(), self._initdays))):
            wvars[f"day{i}rain"] = weather.processed_value(i, "rain")
            wvars[f"day{i}snow"] = weather.processed_value(i, "snow")
            wvars[f"day{i}max"] = weather.processed_value(i, "max_temp")
            wvars[f"day{i}min"] = weather.processed_value(i, "min_temp")

        for i in range(int(max(weather.max_days(), self._initdays))):
            wvars[f"aggregate{i}date"] = weather.processed_value(f"a{i}", "date")
            wvars[f"aggregate{i}precipitation"] = weather.processed_value(f"a{i}", "precipitation")
            wvars[f"aggregate{i}max"] = weather.processed_value(f"a{i}", "max_temp")
            wvars[f"aggregate{i}min"] = weather.processed_value(f"a{i}", "min_temp")

        # forecast provides 7 days of data
        for i in range(0, 6):  # noqa: PIE808
            wvars[f"forecast{i}pop"] =weather.processed_value(f"f{i}", "pop")
            wvars[f"forecast{i}rain"] = weather.processed_value(f"f{i}", "rain")
            wvars[f"forecast{i}snow"] = weather.processed_value(f"f{i}", "snow")
            wvars[f"forecast{i}humidity"] = weather.processed_value(f"f{i}", "humidity")
            wvars[f"forecast{i}max"] = weather.processed_value(f"f{i}", "max_temp")
            wvars[f"forecast{i}min"] = weather.processed_value(f"f{i}", "min_temp")
            wvars[f"forecast{i}wind_deg"] = weather.processed_value(f"f{i}", "wind_deg")
            wvars[f"forecast{i}wind_speed"] = weather.processed_value(f"f{i}", "wind_speed")
            wvars[f"forecast{i}uvi"] = weather.processed_value(f"f{i}", "uvi")
            wvars[f"forecast{i}clouds"] = weather.processed_value(f"f{i}", "clouds")
            wvars[f"forecast{i}description"] = weather.processed_value(f"f{i}", "description")

        # current observations
        wvars["current_rain"] = weather.processed_value("current", "rain")
        wvars["current_snow"] = weather.processed_value("current", "snow")
        wvars["current_humidity"] = weather.processed_value("current", "humidity")
        wvars["current_temp"] = weather.processed_value("current", "temp")
        wvars["current_pressure"] = weather.processed_value("current", "pressure")
        wvars["current_wind_deg"] =  weather.processed_value("current", "wind_deg")
        wvars["current_wind_speed"] = weather.processed_value("current", "wind_speed")
        wvars["current_uvi"] = weather.processed_value("current", "uvi")
        wvars["current_clouds"] = weather.processed_value("current", "clouds")
        wvars["current_description"] = weather.processed_value("current", "description")

        # special values
        wvars["remaining_backlog"] = weather.remaining_backlog()
        wvars["daily_count"] = weather.daily_count()
        wvars["hourly_time"] = weather.processed_value("plotty", "x")
        wvars["hourly_rain"] = weather.processed_value("plotty", "y")

        return wvars

    def list_vars(self):
        """List all available variables."""
        wvars = self._update_vars(self._weather)

        card = "```" + chr(10)
        card += f"Configured max days: {self._maxdays}" + chr(10)
        card += f"Configured initial days: {self._initdays}" + chr(10)
        for name, value in wvars.items():
            card += f"{name}: {value}" + chr(10)
        card += "```" + chr(10)

        async_dismiss(self.hass, "owmhlistsensors")
        async_create(
            self.hass,
            message=card,
            title="OWMH Attributes",
            notification_id="owmhlistsensors",
        )
