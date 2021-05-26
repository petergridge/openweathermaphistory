import logging
from datetime import datetime, timezone, timedelta 
from .data import RestData

# Shortcut for the logger
_LOGGER = logging.getLogger(__name__)


def create_rest_data_from_config(hass, key, lat, lon, day):
    """Create RestData from config."""
        
    units     = "metric"
    dt = int((datetime.now(tz=timezone.utc)- timedelta(days=day)).timestamp())
    resource =  "https://api.openweathermap.org/data/2.5/onecall/timemachine?lat=%s&lon=%s&dt=%s&appid=%s&units=%s" % (lat, lon, dt, key, units)
    method     = "GET"
    payload    = None
    verify_ssl = True
    headers    = None
    params     = None
    auth       = None
    timeout    = 15 #config.get(CONF_TIMEOUT)

    return RestData(
        hass, resource, timeout
    )