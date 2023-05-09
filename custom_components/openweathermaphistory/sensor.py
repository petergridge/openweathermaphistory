"""Platform for historical rain factor Sensor integration."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import homeassistant.helpers.config_validation as cv
import jinja2
import voluptuous as vol
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RESOURCES,
    CONF_TYPE,
    EVENT_HOMEASSISTANT_STOP,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util.unit_system import METRIC_SYSTEM

from .const import (
    ATTR_0_SIG,
    ATTR_1_SIG,
    ATTR_2_SIG,
    ATTR_3_SIG,
    ATTR_4_SIG,
    ATTR_ICON_FINE,
    ATTR_ICON_LIGHTRAIN,
    ATTR_ICON_RAIN,
    ATTR_WATERTARGET,
    CONF_DATA,
    CONF_END_HOUR,
    CONF_FORMULA,
    CONF_LOOKBACK_DAYS,
    CONF_MAX_CALLS_PER_DAY,
    CONF_MAX_CALLS_PER_HOUR,
    CONF_START_HOUR,
    DFLT_ICON_FINE,
    DFLT_ICON_LIGHTRAIN,
    DFLT_ICON_RAIN,
    DFLT_LOOKBACK_DAYS,
    DFLT_MAX_CALLS_PER_DAY,
    DFLT_MAX_CALLS_PER_HOUR,
    SENSOR_TYPES,
    TYPE_BACKFILL_PCT,
    TYPE_CUSTOM,
    TYPE_DEFAULT_FACTOR,
    TYPE_TOTAL_RAIN,
)
from .weatherhistory import WeatherHistory

DEFAULT_NAME = "rainfactor"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_RESOURCES, default=[]): [
            vol.Schema(
                {
                    vol.Required(CONF_NAME): cv.string,
                    vol.Optional(CONF_TYPE): vol.In(SENSOR_TYPES),
                    vol.Optional(CONF_DATA, default={}): vol.Schema(
                        {
                            vol.Optional(ATTR_0_SIG, default=1): cv.positive_float,
                            vol.Optional(ATTR_1_SIG, default=0.5): cv.positive_float,
                            vol.Optional(ATTR_2_SIG, default=0.25): cv.positive_float,
                            vol.Optional(ATTR_3_SIG, default=0.12): cv.positive_float,
                            vol.Optional(ATTR_4_SIG, default=0.06): cv.positive_float,
                            vol.Optional(
                                ATTR_WATERTARGET, default=10
                            ): cv.positive_float,
                            vol.Optional(CONF_FORMULA): cv.string,
                            vol.Optional(CONF_START_HOUR): int,
                            vol.Optional(CONF_END_HOUR): int,
                        }
                    ),
                },
            )
        ],
        vol.Optional(ATTR_ICON_FINE, default=DFLT_ICON_FINE): cv.icon,
        vol.Optional(ATTR_ICON_LIGHTRAIN, default=DFLT_ICON_LIGHTRAIN): cv.icon,
        vol.Optional(ATTR_ICON_RAIN, default=DFLT_ICON_RAIN): cv.icon,
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Required(CONF_LOOKBACK_DAYS, default=DFLT_LOOKBACK_DAYS): cv.positive_int,
        # 1,000 free calls per day on default plan.
        # Set default to 20% lower for some buffer or usage by other apps
        vol.Required(CONF_MAX_CALLS_PER_DAY, default=DFLT_MAX_CALLS_PER_DAY): int,
        # Can set this to a value larger than max per day/24 to allow for
        # a larger burst rate during backfills.
        # We will always reserve up to 24 calls per day to update
        # at least once per hour.  For example, if you set CONF_MAX_CALLS_PER_DAY
        # to 1,000 and CONF_MAX_CALLS_PER_HOUR to 1,000, we will use up to
        # 977 calls in the current hour.  If we use all in the current hour,
        # we will use 1 per hour for the next 23 hours to stay under the max per day.
        vol.Required(CONF_MAX_CALLS_PER_HOUR, default=DFLT_MAX_CALLS_PER_HOUR): int,
    }
)

# default to 30 second intervals.  NOTE: We will not necessarily request from API every interval,
# but only check if we need an hourly live request or continue backfilling if there is more
# backfill needed and we have available rate limits
SCAN_INTERVAL = timedelta(seconds=30)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors from ConfigEntry or Options flow (ui flows)."""
    # first merge options into data to handle updates via reconfigure, then reload
    data = dict(config_entry.data)
    options = dict(config_entry.options)
    data.update(options)
    await async_setup_platform(hass, data, add_entities)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensors."""

    if hass.config.units is METRIC_SYSTEM:
        units = "metric"
    else:
        units = "imperial"

    lat = config.get(CONF_LATITUDE, hass.config.latitude)
    lon = config.get(CONF_LONGITUDE, hass.config.longitude)

    _LOGGER.info("Setting up platform with location %s, %s", lat, lon)

    await _async_setup_entities(add_entities, hass, config, units)

    _LOGGER.info("Platform setup successfully")


async def _async_setup_entities(
    add_entities: AddEntitiesCallback,
    hass: HomeAssistant,
    config: ConfigType,
    units: str,
) -> None:
    _LOGGER.debug("Setting up registry")
    sensor_registry = RainSensorRegistry(
        hass=hass,
        config=config,
        units=units,
    )

    # set up registry polling
    polling_remover = async_track_time_interval(
        hass, sensor_registry.async_update, SCAN_INTERVAL
    )

    @callback
    def _async_stop_polling(*_: Any) -> None:
        polling_remover()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_polling)

    entities = sensor_registry.sensors
    _LOGGER.debug("Adding entities")
    add_entities(entities)

    await sensor_registry.async_load()
    await sensor_registry.async_update()


class RainSensor(SensorEntity):
    def __init__(
        self,
        name: str,
        location: str,
        type: str,
        icon: str,
        data=None,
        value=None,
    ):
        self._attr_name: str = name
        self.location: str = location
        self.value: float | None = value
        self.type: str = type
        self.data: ConfigType | None = data
        self._icon: str = icon
        self.update_time: datetime | None = None
        if self.type == TYPE_BACKFILL_PCT:
            self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def icon(self) -> str:
        return self._icon

    @property
    def unique_id(self):
        """Return a unique_id for this entity."""
        return f"{self._attr_name}_{self.location}"

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def state_class(self) -> SensorStateClass:
        return SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        # round this for now, suggested_display_precision appears to not
        # be working as described in the docs
        if self.value is None:
            return self.value
        return round(self.value, self.suggested_display_precision)

    @property
    def suggested_display_precision(self) -> int:
        """Return the number of digits after the decimal point for the sensor's state."""
        return 2

    def handle_update(self) -> None:
        self.async_write_ha_state()


class RainSensorRegistry:
    """Registry of name to sensor data"""

    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigType,
        units: str,
    ):
        self._hass = hass
        self._registry: dict[str, RainSensor] = {}
        self._weather_history = WeatherHistory(hass, config, units)

        self._icon_fine = config.get(ATTR_ICON_FINE, DFLT_ICON_FINE)
        self._icon_lightrain = config.get(ATTR_ICON_LIGHTRAIN, DFLT_ICON_LIGHTRAIN)
        self._icon_rain = config.get(ATTR_ICON_RAIN, DFLT_ICON_RAIN)

        for resource in config[CONF_RESOURCES]:
            type_ = resource[CONF_TYPE]
            name = resource[CONF_NAME]
            data = None

            if CONF_DATA in resource:
                data = resource[CONF_DATA]

            if type_ == TYPE_CUSTOM:
                if (data is None) or (CONF_FORMULA not in data):
                    _LOGGER.warn(
                        "Could not setup custom type with no formula. skipping"
                    )
                    continue

            elif type_ == TYPE_TOTAL_RAIN:
                if (
                    (data is None)
                    or (CONF_START_HOUR not in data)
                    or (CONF_END_HOUR not in data)
                ):
                    _LOGGER.warn(
                        "Could not setup total rain type without start and end hour. skipping"
                    )
                    continue
                start_hour = int(data[CONF_START_HOUR])
                end_hour = int(data[CONF_END_HOUR])

                if start_hour > end_hour:
                    _LOGGER.warn(
                        "Could not setup total rain type without start hour > end hour. skipping. %s",
                        data,
                    )
                    continue
                if end_hour > 0:
                    _LOGGER.warn(
                        "Could not setup total rain type without end hour > 0. skipping. %s",
                        data,
                    )
                    continue

            self._registry[name] = RainSensor(
                name=name,
                location=self._weather_history.location,
                value=None,
                type=type_,
                data=data,
                icon=self._icon_lightrain,
            )

    @property
    def sensors(self) -> list[RainSensor]:
        return list(self._registry.values())

    def _update_vars(self, weather_history: WeatherHistory):
        vars: dict[str, Any] = {}
        for i in range(weather_history.lookback_days):
            vars[f"day{i}rain"] = weather_history.day_rain(i)
            vars[f"day{i}snow"] = weather_history.day_snow(i)
            vars[f"day{i}humidity"] = weather_history.day_humidity(i)
            vars[f"day{i}temp_high"] = weather_history.day_temp_high(i)
            vars[f"day{i}temp_low"] = weather_history.day_temp_low(i)
        vars["max"] = max
        vars["min"] = min
        vars["sum"] = sum

        return vars

    def _evaluate_custom_formula(self, formula: str, vars: dict[str, Any]) -> float:
        environment = jinja2.Environment()
        template = environment.from_string("{{" + formula + "}}")
        try:
            return float(template.render(vars))
        except Exception as e:
            _LOGGER.warn("Could not evaluate custom formula: %s. \n %s", formula, e)
            return 0

    def _evaluate_default_factor(self, rs: RainSensor, vars: dict[str, Any]) -> float:
        if rs.data is None:
            return 1

        watertarget = rs.data.get(ATTR_WATERTARGET, 10)
        if watertarget == 0:
            return 0

        day0sig = rs.data.get(ATTR_0_SIG, 1)
        day1sig = rs.data.get(ATTR_1_SIG, 0.5)
        day2sig = rs.data.get(ATTR_2_SIG, 0.25)
        day3sig = rs.data.get(ATTR_3_SIG, 0.12)
        day4sig = rs.data.get(ATTR_4_SIG, 0.06)

        formula = f"max( ({watertarget} - day0rain*{day0sig} - day1rain*{day1sig} - \
                day2rain*{day2sig} - day3rain*{day3sig} - day4rain*{day4sig}) / {watertarget}, 0)"
        return self._evaluate_custom_formula(formula, vars)

    def _evaluate_total_rain(self, rs: RainSensor) -> float:
        assert rs.data is not None
        # `start_hour` and `end_hour` are offsets from the current hour.
        # For example, start_hour=-24, end_hour=0 would show the last 24hours of data.
        start_hour: int = rs.data[CONF_START_HOUR]
        end_hour: int = rs.data[CONF_END_HOUR]
        now = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)

        start = now + timedelta(hours=start_hour)
        end = now + timedelta(hours=end_hour)

        return self._weather_history.total_attr(start, end, "rain")

    async def async_update(self, update_time=None):
        _LOGGER.debug("SensorRegistry updating, %s", update_time)
        # Update for current time if needed
        await self._weather_history.async_update()
        # Continue backfill if needed in a background task
        self._hass.async_create_task(self._weather_history.backfill_chunk())

        self.update_sensor_data()

    async def async_load(self):
        """Load weather history data from persistent storage"""
        await self._weather_history.async_load()

    def update_sensor_data(self):
        _LOGGER.debug("Updating sensor data")
        vars = self._update_vars(self._weather_history)

        for name in self._registry:
            sensor = self._registry[name]
            _LOGGER.debug("Updating %s: %s", name, sensor)

            if sensor.type == TYPE_CUSTOM:
                sensor.value = self._evaluate_custom_formula(
                    sensor.data[CONF_FORMULA], vars
                )
                sensor.update_time = datetime.now()

            elif sensor.type == TYPE_DEFAULT_FACTOR:
                sensor.value = self._evaluate_default_factor(sensor, vars)
                if sensor.value == 1:
                    sensor._icon = self._icon_fine
                elif sensor.value == 0:
                    sensor._icon = self._icon_rain
                else:
                    sensor._icon = self._icon_lightrain

                sensor.update_time = datetime.now()

            elif sensor.type == TYPE_TOTAL_RAIN:
                sensor.value = self._evaluate_total_rain(sensor)

            elif sensor.type == TYPE_BACKFILL_PCT:
                sensor.value = self._weather_history.backfill_pct

            sensor.handle_update()
            _LOGGER.debug(
                "Updated %s: %s. value: %s", name, sensor, sensor.native_value
            )
