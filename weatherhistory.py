"""Support for RESTful API."""
import logging
import json
import math
from datetime import datetime, timedelta, timezone

_LOGGER = logging.getLogger(__name__)

class WeatherHist:
    """Class for handling the data retrieval."""

    def __init__(self):
        """Initialize the data object."""
        self._weather = None
        self._daymin  = None
        self._daymax  = None
        self.attrs    = None
        self.factor   = None

    async def set_weather(self, weather, daymin, daymax):
        """Set url."""
        self._weather = weather
        self._daymin  = daymin
        self._daymax  = daymax

    async def async_update(self):
        _LOGGER.debug("updating weatherhistory")
        n = 0
        minfac = 1
        ATTRS = {}
        ATTRSRAIN = {}
        ATTRSCUM = {}
        ATTRMIN = {}
        ATTRMAX = {}
        cumulative = 0
        for rest in self._weather:

            data = json.loads(rest.data)
            total = 0
            mintemp = 999
            maxtemp = -999
            hourly = data["hourly"]
            for hour in hourly:
                #the latest time for the current day
                if n == 0:
                    if 'dt' in hour:
                        dt = hour["dt"]
                        formatted_dt = datetime.utcfromtimestamp(dt).replace(tzinfo=timezone.utc).astimezone(tz=None).strftime('%Y-%m-%d %H:%M:%S')
                        ATTRS ["As at"] = formatted_dt
                        _LOGGER.debug("AS AT %s",formatted_dt)
                if 'rain' in hour:
                    rain = hour["rain"]
                    if math.isnan(rain["1h"]):
                        rain["1h"] = 0
                    else:
                        total += rain["1h"]
                if 'temp' in hour:
                    if hour["temp"] < mintemp:
                        mintemp = hour["temp"]
                        ATTRMIN["day_%d_min"%(n)] = mintemp
                    if hour["temp"] > maxtemp:
                        maxtemp = hour["temp"]
                        ATTRMAX["day_%d_max"%(n)] = maxtemp
                    
            #end hour loop

            cumulative = cumulative + total
            ATTRSCUM ["day_%d_cumulative"%(n)] = round(cumulative,2)
            ATTRSRAIN ["day_%d_rain"%(n)] = round(total,2)
            try:
                dayfac = 1 - ( cumulative - self._daymin[n])/(self._daymax[n]-self._daymin[n])
                if dayfac < minfac:
                    minfac = dayfac
            except:
                dayfac = 1
            n += 1
        #end rest loop
        if minfac < 0:
            minfac = 0

        self.factor = minfac
        self.attrs = {**ATTRS, **ATTRSRAIN, **ATTRMIN, **ATTRMAX}
