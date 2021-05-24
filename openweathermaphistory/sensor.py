"""Platform for historical rain factor Sensor integration."""
import logging
import voluptuous as vol
import requests
import json
import math
from datetime import datetime, timezone, timedelta
from . import create_rest_data_from_config
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
)

from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    ATTR_ICON,
    )
from .const import (
    DOMAIN,
    ATTR_DAYS,
    ATTR_0_MAX,
    ATTR_0_MIN,
    ATTR_1_MAX,
    ATTR_1_MIN,
    ATTR_2_MAX,
    ATTR_2_MIN,
    ATTR_3_MAX,
    ATTR_3_MIN,
    ATTR_4_MAX,
    ATTR_4_MIN,
    ATTR_5_MAX,
    ATTR_5_MIN,
    DFLT_ICON_FINE,
    DFLT_ICON_LIGHTRAIN,
    DFLT_ICON_RAIN,
    ATTR_ICON_FINE,
    ATTR_ICON_LIGHTRAIN,
    ATTR_ICON_RAIN,
    )
import homeassistant.helpers.config_validation as cv

DEFAULT_NAME = "rainfactor"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Optional(ATTR_DAYS, default=5):vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
        vol.Optional(ATTR_0_MIN, default=1): cv.positive_int,
        vol.Optional(ATTR_0_MAX, default=5): cv.positive_int,
        vol.Optional(ATTR_1_MIN, default=6): cv.positive_int,
        vol.Optional(ATTR_1_MAX, default=10): cv.positive_int,
        vol.Optional(ATTR_2_MIN, default=11): cv.positive_int,
        vol.Optional(ATTR_2_MAX, default=15): cv.positive_int,
        vol.Optional(ATTR_3_MIN, default=16): cv.positive_int,
        vol.Optional(ATTR_3_MAX, default=20): cv.positive_int,
        vol.Optional(ATTR_4_MIN, default=21): cv.positive_int,
        vol.Optional(ATTR_4_MAX, default=25): cv.positive_int,
        vol.Optional(ATTR_5_MIN, default=26): cv.positive_int,
        vol.Optional(ATTR_5_MAX, default=30): cv.positive_int,
        vol.Optional(ATTR_ICON_FINE, default=DFLT_ICON_FINE): cv.icon,
        vol.Optional(ATTR_ICON_LIGHTRAIN, default=DFLT_ICON_LIGHTRAIN): cv.icon,
        vol.Optional(ATTR_ICON_RAIN, default=DFLT_ICON_RAIN): cv.icon,
    }
)

SCAN_INTERVAL = timedelta(seconds=3600) #default to one hour intervals

_LOGGER = logging.getLogger(__name__)

async def _async_create_entities(hass, config, weather):
    """Create the Template switches."""
    sensors = []

    name      = config[CONF_NAME]
    days      = config[ATTR_DAYS]
    day0max   = config[ATTR_0_MAX]
    day0min   = config[ATTR_0_MIN]
    day1max   = config[ATTR_1_MAX]
    day1min   = config[ATTR_1_MIN]
    day2max   = config[ATTR_2_MAX]
    day2min   = config[ATTR_2_MIN]
    day3max   = config[ATTR_3_MAX]
    day3min   = config[ATTR_3_MIN]
    day4max   = config[ATTR_4_MAX]
    day4min   = config[ATTR_4_MIN]
    day5max   = config[ATTR_5_MAX]
    day5min   = config[ATTR_5_MIN]
    icon_fine = config[ATTR_ICON_FINE]
    icon_lightrain = config[ATTR_ICON_LIGHTRAIN]
    icon_rain = config[ATTR_ICON_RAIN]

    daymax = [day0max,day1max,day2max,day3max,day4max,day5max]
    daymin = [day0min,day1min,day2min,day3min,day4min,day5min]

    sensors.append(
        RainFactor(
            hass,
            config,
            weather,
            name,
            days,
            icon_fine,
            icon_lightrain,
            icon_rain,
            daymin,
            daymax,
        )
    )

    return sensors


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the sensors."""
    weather = []
    days    = config[ATTR_DAYS]

    for n in range(days + 1):
        rest = create_rest_data_from_config(hass, config, n)
        await rest.async_update(log_errors=False)
        weather.append (rest)

    async_add_entities(await _async_create_entities(hass, config, weather))


class RainFactor(SensorEntity):

    def __init__(
        self,
        hass,
        config,
        weather,
        name: str,
        days: float,
        icon_fine,
        icon_lightrain,
        icon_rain,
        daymin: list,
        daymax: list,
    ):
        """Initialize the sensor."""
        self._name = name
        self.hass = hass
        self._config = config
        self._weather = weather
        self._state = 1
        self._daymin = daymin
        self._daymax = daymax
        self._state_attributes   = None
        self._icon_fine = icon_fine
        self._icon_lightrain = icon_lightrain
        self._icon_rain = icon_rain
        self._ran_today = datetime.today().strftime('%Y-%m-%d')

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return the unit of measurement."""
        return self._icon

    @property
    def state_attributes(self):
        """Return the state attributes.
        Implemented by component base class.
        """
        return self._state_attributes


    async def async_added_to_hass(self):
        n = 0
        minfac = 1
        ATTRS = {}
        cumulative = 0
        for rest in self._weather:
            data = json.loads(rest.data)
            total = 0
            hourly = data["hourly"]
            for hour in hourly:
                if 'rain' in hour:
                    rain = hour["rain"]
                    if math.isnan(rain["1h"]):
                        rain["1h"] = 0
                    else:
                        total += rain["1h"]
            cumulative = cumulative + total
            ATTRS ["day_%d_cumulative"%(n)] = round(cumulative,2)
            ATTRS ["day_%d_rain"%(n)] = round(total,2)
            try:
                dayfac = 1 - ( cumulative - self._daymin[n])/(self._daymax[n]-self._daymin[n])
                if dayfac < minfac:
                    minfac = dayfac
            except:
                dayfac = 1

            n += 1

        if minfac < 0:
            minfac = 0

        self._state = minfac
        if minfac == 0:
            self._icon = DFLT_ICON_RAIN
        elif minfac == 1:
            self._icon = DFLT_ICON_FINE
        else:
            self._icon = DFLT_ICON_LIGHTRAIN

        setattr(self, '_state_attributes', ATTRS)

        self.async_write_ha_state()

        await super().async_added_to_hass()

    async def async_update(self):
        #first time today reload the weather for all days        
        justloaded = False
        if self._ran_today != datetime.today().strftime('%Y-%m-%d'):
            #reload the weather
            self._ran_today = datetime.today().strftime('%Y-%m-%d')
            weather = []
            days    = config[ATTR_DAYS]
            justloaded = True
            for n in range(days + 1):
                rest = create_rest_data_from_config(hass, config, n)
                await rest.async_update(log_errors=False)
                weather.append (rest)

        n = 0
        minfac = 1
        ATTRS = {}
        cumulative = 0
        for  rest in self._weather:
            #only update today's weather previous days won't change
            if n == 0 and not justloaded:
                await rest.async_update(log_errors=False)

            data = json.loads(rest.data)
            total = 0
            hourly = data["hourly"]
            for hour in hourly:
                if 'rain' in hour:
                    rain = hour["rain"]
                    if math.isnan(rain["1h"]):
                        rain["1h"] = 0
                    else:
                        total += rain["1h"]
            cumulative = cumulative + total
            ATTRS ["day_%d_cumulative"%(n)] = round(cumulative,2)
            ATTRS ["day_%d_rain"%(n)] = round(total,2)
            try:
                dayfac = 1 - (cumulative - self._daymin[n])/(self._daymax[n]-self._daymin[n])
                if dayfac < minfac:
                    minfac = dayfac
            except:
                dayfac = 1
            n += 1

        if minfac < 0:
            minfac = 0
        if minfac == 0:
            self._icon = "mdi:weather-pouring"
        elif minfac == 1:
            self._icon = "mdi:weather-sunny"
        else:
            self._icon = "mdi:weather-rainy"

        self._state = minfac

        setattr(self, '_state_attributes', ATTRS)

        self.async_write_ha_state()
