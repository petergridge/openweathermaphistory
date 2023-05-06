"""Platform for historical rain factor Sensor integration."""

#CONFIG FLOW
#Validations to implement:
#lat/lon are unique for all instances
#formula's are unique within an instance

#features
#build a unique id, CONFIG_ID + sensor instance number (not reusable)
#validate SensorStateClass,SensorDeviceClass
#allocate SensorStateClass,SensorDeviceClass automatically where it can be identified
#delete file when removing integration


from .weatherhistory import Weather

import logging
import voluptuous as vol
from datetime import  timedelta
import jinja2
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    )
from .const import (
    CONF_FORMULA,
    CONF_RESOURCES,
    CONF_ATTRIBUTES,
    CONF_MAX_DAYS,
    CONF_INTIAL_DAYS,
    CONF_PRECISION,
    CONF_STATECLASS,
    CONF_SENSORCLASS,
    )

DEFAULT_NAME = "Open Weather Map History"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_MAX_DAYS, default=5): cv.positive_int,
        vol.Optional(CONF_INTIAL_DAYS, default=5): cv.positive_int,
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Optional(CONF_RESOURCES, default=[]): [
            vol.Schema(
                {
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_FORMULA): cv.string,
                vol.Optional(CONF_ATTRIBUTES): cv.string,
#                vol.Optional(CONF_PRECISION): cv.positive_int,
                vol.Optional(CONF_SENSORCLASS): cv.string,
                vol.Optional(CONF_STATECLASS): cv.string,
                },
            )
        ],
    }
)

SCAN_INTERVAL = timedelta(seconds=300)

_LOGGER = logging.getLogger(__name__)

async def _async_create_entities(hass:HomeAssistant, config, weather):
    """Create the Template switches."""
    sensors = []
    coordinator = WeatherCoordinator(hass, config, weather)
    #append multiple sensors using the single weather class
    for resource in config[CONF_RESOURCES]:
        sensors.append(
            WeatherHistory(
                hass,
                config,
                resource,
                weather,
                coordinator
            )
        )
    return sensors

async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    """Set up the sensors."""
    #define a weather class for this instance
    weather = Weather(hass,config)
    await weather.async_update(1)
    async_add_entities(await _async_create_entities(hass, config, weather))

class WeatherCoordinator(DataUpdateCoordinator):
    """Weather API data coordinator
       refresh the data independantly of the sensor"""

    def __init__(self, hass: HomeAssistant, config, weather) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Weather History",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=SCAN_INTERVAL,
        )
        self._hass = hass
        self._config = config
        self._weather = weather

    async def _async_update_data(self):
        """Fetch data from API endpoint"""
        await self._weather.async_update(120)

class WeatherHistory(CoordinatorEntity,SensorEntity):
    ''' Rain factor class defn'''
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        config,
        resource,
        weatherhist: Weather,
        coordinator

    ) -> None:
        #subscribe to the API data coordinator
        super().__init__(coordinator)

        self._hass               = hass
        self._config             = config
        self._state              = 1
        self._weatherhist        = weatherhist
        self._extra_attributes   = None
        self._name               = resource[CONF_NAME]
        self._formula            = resource[CONF_FORMULA]
        self._attributes         = resource.get(CONF_ATTRIBUTES)
        self._precision          = resource.get(CONF_PRECISION,None)
        self._initdays           = config.get(CONF_INTIAL_DAYS)
        self._sensor_class       = resource.get(CONF_SENSORCLASS,None)
        self._state_class       = resource.get(CONF_STATECLASS,None)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.determine_state()
        self.async_write_ha_state()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique_id for this entity."""
        name  = self._config.get(CONF_NAME,DEFAULT_NAME)
        lat   = self._config.get(CONF_LATITUDE,self._hass.config.latitude)
        lon   = self._config.get(CONF_LONGITUDE,self._hass.config.longitude)
        return f"{name}{self._name}{lat}{lon}"

    @property
    def state_class(self) -> SensorStateClass:
        """handle string instances"""
        match self._state_class:
            case 'measurement':
                return SensorStateClass.MEASUREMENT
            case 'total':
                return SensorStateClass.TOTAL
            case 'total_increasing':
                return SensorStateClass.TOTAL_INCREASING
            case _:
                if isinstance(self._state,str):
                    return
                return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self):
        match self._sensor_class:
            case 'humidity':
                return '%'
            case 'precipitation':
                return 'mm'
            case 'precipitation_intensity':
                return 'mm/h'
            case 'temperature':
                return  '°C'

    @property
    def device_class(self) -> SensorDeviceClass:
        """handle string instances"""
        match self._sensor_class:
            case 'humidity':
                return SensorDeviceClass.HUMIDITY
            case 'precipitation':
                return SensorDeviceClass.PRECIPITATION
            case 'precipitation_intensity':
                return SensorDeviceClass.PRECIPITATION_INTENSITY
            case 'temperature':
                return SensorDeviceClass.TEMPERATURE
            case 'pressure':
                return SensorDeviceClass.PRESSURE
            case _:
                return

    @property
    def native_value(self):
        """Return the state."""
        return self._state

    @property
    def suggested_display_precision(self):
        """Return the number of digits after the decimal point"""
        if self._sensor_class is not None:
            return 2

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._extra_attributes

    async def async_added_to_hass(self):
        self._hass.async_create_task(self.async_update())
        await super().async_added_to_hass()

    def determine_state(self):
        """Determine the sensor state"""
        try:
            self._state = float(self._evaluate_custom_formula(self._formula ,  self._update_vars(self._weatherhist)))
        except ValueError:
            self._state = self._evaluate_custom_formula(self._formula ,  self._update_vars(self._weatherhist))
        #return the attributes if requested
        if self._attributes is not None:
            self._extra_attributes = self._evaluate_custom_attr(self._attributes, self._update_vars(self._weatherhist))

    async def async_update(self):
        ''' update the sensor'''
        self.determine_state()
        self.async_write_ha_state()

    def _evaluate_custom_formula(self, formula: str, wvars: dict):
        """evaluate the formula/template"""
        environment = jinja2.Environment()
        if formula.strip().startswith('{%'):
            template = environment.from_string(formula)
        else:
            template = environment.from_string("{{" + formula + "}}")
        #process the template and handle errors
        try:
            return template.render(wvars)
        except jinja2.UndefinedError as exc:
            _LOGGER.warning("Could not evaluate custom formula: %s \n %s", formula, exc)
            return 0
        except jinja2.TemplateSyntaxError as exc:
            _LOGGER.warning("Could not evaluate custom formula: %s \n %s", formula, exc)
            return 0

    def _evaluate_custom_attr(self, attributes: list, wvars: dict):
        """take the list of vars and build the attrs dictionaty"""
        attrs = {}
        attrs_list = attributes.replace(" ","").replace("'","").strip("[]'").split(",")
        for item in attrs_list:
            if item in wvars:
                attrs.update({item:wvars[item]})
        return attrs

    def _update_vars(self, weather_history:Weather):
        wvars = {}
        #default to initial days variable
        for i in range(max(weather_history.num_days(),self._initdays)):
            wvars[f"day{i}rain"]        = weather_history.processed_value(i,'rain')
            wvars[f"day{i}snow"]        = weather_history.processed_value(i,'snow')
            wvars[f"day{i}humidity"]    = weather_history.processed_value(i,'humidity')
            wvars[f"day{i}max"]         = weather_history.processed_value(i,'max_temp')
            wvars[f"day{i}min"]         = weather_history.processed_value(i,'min_temp')
        #forecast provides 8 days of data
        for i in range(0,7):
            wvars[f"forecast{i}pop"]      = weather_history.processed_value(f'f{i}','pop')
            wvars[f"forecast{i}rain"]     = weather_history.processed_value(f'f{i}','rain')
            wvars[f"forecast{i}snow"]     = weather_history.processed_value(f'f{i}','snow')
            wvars[f"forecast{i}humidity"] = weather_history.processed_value(f'f{i}','humidity')
            wvars[f"forecast{i}max"]      = weather_history.processed_value(f'f{i}','max_temp')
            wvars[f"forecast{i}min"]      = weather_history.processed_value(f'f{i}','min_temp')
        #current observations
        wvars["current_rain"]        = weather_history.processed_value('current', 'rain')
        wvars["current_snow"]        = weather_history.processed_value('current', 'snow')
        wvars["current_humidity"]    = weather_history.processed_value('current', 'humidity')
        wvars["current_temp"]        = weather_history.processed_value('current', 'temp')
        wvars["current_pressure"]    = weather_history.processed_value('current', 'pressure')
        #provide additional functions
        wvars["max"]                = max
        wvars["min"]                = min
        wvars["sum"]                = sum
        return wvars
