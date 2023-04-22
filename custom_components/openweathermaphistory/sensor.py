"""Platform for historical rain factor Sensor integration."""
from .weatherhistory import WeatherHist
from .data import RestData

import logging
import voluptuous as vol
from datetime import datetime, timedelta, date
from homeassistant.util.unit_system import METRIC_SYSTEM
import pickle
from os.path import exists , join

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
)

from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    )

from .const import (
    CONST_API_CALL,
    ATTR_API_VER,
    ATTR_0_SIG,
    ATTR_1_SIG,
    ATTR_2_SIG,
    ATTR_3_SIG,
    ATTR_4_SIG,
    ATTR_WATERTARGET,
    ATTR_ICON_FINE,
    ATTR_ICON_LIGHTRAIN,
    ATTR_ICON_RAIN,
    DFLT_ICON_FINE,
    DFLT_ICON_LIGHTRAIN,
    DFLT_ICON_RAIN,
    )
import homeassistant.helpers.config_validation as cv

DEFAULT_NAME = "rainfactor"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(ATTR_API_VER, default=1): cv.positive_int,
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,

        vol.Optional(ATTR_0_SIG, default=1.0): cv.positive_float,
        vol.Optional(ATTR_1_SIG, default=0.5): cv.positive_float,
        vol.Optional(ATTR_2_SIG, default=0.25): cv.positive_float,
        vol.Optional(ATTR_3_SIG, default=0.12): cv.positive_float,
        vol.Optional(ATTR_4_SIG, default=0.06): cv.positive_float,
        vol.Optional(ATTR_WATERTARGET, default=10): cv.positive_float,

        vol.Optional(ATTR_ICON_FINE, default=DFLT_ICON_FINE): cv.icon,
        vol.Optional(ATTR_ICON_LIGHTRAIN, default=DFLT_ICON_LIGHTRAIN): cv.icon,
        vol.Optional(ATTR_ICON_RAIN, default=DFLT_ICON_RAIN): cv.icon,
    }
)

SCAN_INTERVAL = timedelta(seconds=3600) #default to 60 minute intervals

_LOGGER = logging.getLogger(__name__)

async def _async_create_entities(hass, config): #, weather):
    """Create the Template switches."""
    sensors = []
    name      = config[CONF_NAME]
    daysig = [config[ATTR_0_SIG],config[ATTR_1_SIG],config[ATTR_2_SIG],config[ATTR_3_SIG],config[ATTR_4_SIG]]
    watertarget = config[ATTR_WATERTARGET]

    if hass.config.units is METRIC_SYSTEM:
        units = 'metric'
    else:
        units = 'imperial'

    sensors.append(
        RainFactor(
            hass,
            config,
            name,
            daysig,
            watertarget,
            units
        )
    )

    return sensors

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the sensors."""
#    weather = []
    async_add_entities(await _async_create_entities(hass, config))

class RainFactor(SensorEntity):
    ''' Rain factor class defn'''
    _attr_has_entity_name = True

    def __init__(
        self,
        hass,
        config,
        name: str,
        daysig: list,
        watertarget,
        units
    ):
        """Initialize the sensor."""
        self._name               = name
        self._hass               = hass
        self._state              = 1
        self._daysig             = daysig
        self._watertarget        = watertarget

        self._extra_attributes   = None
        self._icon               = config[ATTR_ICON_FINE]
        self._icon_fine          = config[ATTR_ICON_FINE]
        self._icon_lightrain     = config[ATTR_ICON_LIGHTRAIN]
        self._icon_rain          = config[ATTR_ICON_RAIN]
        self._key                = config[CONF_API_KEY]
        self._units              = units

        self._lat = config.get(CONF_LATITUDE,hass.config.latitude)
        self._lon = config.get(CONF_LONGITUDE,hass.config.longitude)
        self._timezone = config.get(CONF_LONGITUDE,hass.config.time_zone)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique_id for this entity."""
        return f"{self._name}-{self._lat}-{self._lon}"

    @property
    def native_value(self):
        """Return the state."""
        return self._state

    @property
    def icon(self):
        """Return the unit of measurement."""
        return self._icon

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._extra_attributes

    def get_stored_data(self):
        """Return stored data."""
        file = join(self._hass.config.path(), 'rainfactor' + '.pickle')
        if not exists(file):
            return {}
        with open(file, 'rb') as myfile:
            content = pickle.load(myfile)
        myfile.close()
        return content

    async def async_added_to_hass(self):

        #run the update in a seperate non blocking task
        self._hass.async_create_task(self.async_update())

        await super().async_added_to_hass()
        _LOGGER.debug('added to hass has run successfully')

    async def async_update(self):
        ''' update the sensor'''

        weather = []
        rest = RestData()
        hour = datetime(date.today().year, date.today().month, date.today().day,datetime.now().hour)
        dt = int(datetime.timestamp(hour))

        #if the pickle file is deleted reload all days
        lastdt = dt - 3600*24*5
        #determine when the last update was done
        #incase a refresh is missed
        weatherdata = self.get_stored_data()
        for hhour in weatherdata.keys():
            if hhour > lastdt:
                lastdt = hhour

        i = (dt - lastdt)/3600
        while i > 0 :
            url = CONST_API_CALL % (self._lat,self._lon, dt, self._key, self._units)
            rest = RestData()
            await rest.set_resource(self._hass, url)
            await rest.async_update(log_errors=False)
            weather.append (rest)
            i -= 1
            dt -= 3600

        #now call the weather
        weatherhist = WeatherHist()
        await weatherhist.set_weather(weather, self._daysig, self._watertarget, self._units, self._timezone, self._hass, self._name)
        await weatherhist.async_update()

        self._extra_attributes = weatherhist.attrs
        self._state = weatherhist.factor

        if weatherhist.factor == 0:
            self._icon = self._icon_rain
        elif weatherhist.factor == 1:
            self._icon = self._icon_fine
        else:
            self._icon = self._icon_lightrain
        weatherhist = None
        self.async_write_ha_state()
