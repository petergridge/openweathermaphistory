"""Platform for historical rain factor Sensor integration."""
from .weatherhistory import WeatherHist
from .data import RestData

import logging
import voluptuous as vol
import json
import math
from datetime import datetime, timedelta, timezone
#from . import create_rest_data_from_config , create_weatherhist
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
)

from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_UNIT_SYSTEM,
    CONF_UNIT_SYSTEM_METRIC
    )
from .const import (
    DOMAIN,
    CONST_API_CALL,
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
        vol.Optional(CONF_UNIT_SYSTEM, default=CONF_UNIT_SYSTEM_METRIC): cv.unit_system,
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

    daymax = [day0max,day1max,day2max,day3max,day4max,day5max]
    daymin = [day0min,day1min,day2min,day3min,day4min,day5min]

    sensors.append(
        RainFactor(
            hass,
            config,
            weather,
            name,
            days,
            daymin,
            daymax,
        )
    )

    return sensors


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the sensors."""
    weather = []
    days    = config[ATTR_DAYS]
    key     = config[CONF_API_KEY]
    units   = config[CONF_UNIT_SYSTEM]
    try:
        lat = config[CONF_LATITUDE]
        lon = config[CONF_LONGITUDE]
    except:
        lat = hass.config.latitude
        lon = hass.config.longitude

    for n in range(days + 1):
        rest = RestData()
        dt = int((datetime.now(tz=timezone.utc)- timedelta(days=n)).timestamp())
        url = CONST_API_CALL % (lat, lon, dt, key, units)
        await rest.set_resource(hass, url)
        await rest.async_update(log_errors=False)
        weather.append (rest)

    async_add_entities(await _async_create_entities(hass, config, weather))
    _LOGGER.debug('setup_platform has run successfully')


class RainFactor(SensorEntity):

    def __init__(
        self,
        hass,
        config,
        weather,
        name: str,
        days: float,
        daymin: list,
        daymax: list,
    ):
        """Initialize the sensor."""
        self._name               = name
        self._hass               = hass
        self._days               = days
        self._config             = config
        self._weather            = weather
        self._state              = 1
        self._daymin             = daymin
        self._daymax             = daymax
        self._state_attributes   = None
        self._icon_fine          = config[ATTR_ICON_FINE]
        self._icon_lightrain     = config[ATTR_ICON_LIGHTRAIN]
        self._icon_rain          = config[ATTR_ICON_RAIN]
        self._ran_today          = datetime.utcnow().date().strftime('%Y-%m-%d')
        self._key                = config[CONF_API_KEY]
        self._units              = config[CONF_UNIT_SYSTEM]
        try:
            self._lat = config[CONF_LATITUDE]
            self._lon = config[CONF_LONGITUDE]
        except:
            self._lat = hass.config.latitude
            self._lon = hass.config.longitude

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

        self._weatherhist = WeatherHist()
        await self._weatherhist.set_weather(self._weather, self._daymin, self._daymax)
        await self._weatherhist.async_update()        
        
        setattr(self, '_state_attributes', self._weatherhist.attrs)

        self._state = self._weatherhist.factor

        if self._weatherhist.factor == 0:
            self._icon = self._icon_rain
        elif self._weatherhist.factor == 1:
            self._icon = self._icon_fine
        else:
            self._icon = self._icon_lightrain

        self.async_write_ha_state()
        await super().async_added_to_hass()
        _LOGGER.debug('added to hass has run successfully')


    async def async_update(self):
        #first time today reload the weather for all days
        if self._ran_today != datetime.utcnow().date().strftime('%Y-%m-%d'):
            #reload all weather on a new day
            self._ran_today = datetime.utcnow().date().strftime('%Y-%m-%d')
            n = 0
            for rest in self._weather:
                dt = int((datetime.now(tz=timezone.utc)- timedelta(days=n)).timestamp())
                url = CONST_API_CALL % (self._lat,self._lon,dt,self._key,self._units)
                await rest.set_resource(self._hass,url)
                await rest.async_update(log_errors=False)
                n += 1
            _LOGGER.debug('new day update has run successfully')
        else:
            #only reload today's weather
            _LOGGER.debug("weather 0 before")
            _LOGGER.debug(self._weather[0].data)
            await self._weather[0].async_update(log_errors=False)
            _LOGGER.debug("weather 0 after")
            _LOGGER.debug(self._weather[0].data)

        await self._weatherhist.set_weather(self._weather, self._daymin, self._daymax) 
        await self._weatherhist.async_update()        
        
        setattr(self, '_state_attributes', self._weatherhist.attrs)

        self._state = self._weatherhist.factor

        if self._weatherhist.factor == 0:
            self._icon = self._icon_rain
        elif self._weatherhist.factor == 1:
            self._icon = self._icon_fine
        else:
            self._icon = self._icon_lightrain

        self.async_write_ha_state()
        _LOGGER.debug('sensor update successful')

