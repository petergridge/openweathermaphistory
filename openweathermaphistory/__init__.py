import logging
from datetime import datetime, timezone, timedelta 
from .data import RestData

#from .const import (
#    DOMAIN,
#    SENSOR_ID_FORMAT,
#    CONST_SENSOR,
#    )


from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_TIMEOUT,
    )

# Shortcut for the logger
_LOGGER = logging.getLogger(__name__)


def create_rest_data_from_config(hass, config, day):
    """Create RestData from config."""

    key       = config[CONF_API_KEY]
    try:
        lat       = config[CONF_LATITUDE]
        lon       = config[CONF_LONGITUDE]
    except:
        lat = hass.config.latitude
        lon = hass.config.longitude
        
    units     = "metric"
    dt = int((datetime.now(tz=timezone.utc)- timedelta(days=day)).timestamp())
    resource =  "https://api.openweathermap.org/data/2.5/onecall/timemachine?lat=%s&lon=%s&dt=%s&appid=%s&units=%s" % (lat, lon, dt, key ,units)
    method     = "GET"
    payload    = None
    verify_ssl = True
    headers    = None
    params     = None
    auth       = None
    timeout    = 15 #config.get(CONF_TIMEOUT)

    return RestData(
        hass, method, resource, auth, headers, params, payload, verify_ssl, timeout
    )