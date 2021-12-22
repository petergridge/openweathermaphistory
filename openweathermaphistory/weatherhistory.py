"""Support for RESTful API."""
import logging
import json
import math
from datetime import datetime, timedelta, timezone
import pytz

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
        MINTEMP = {0:999,1:999,2:999,3:999,4:999,5:999}
        MAXTEMP = {0:-999,1:-999,2:-999,3:-999,4:-999,5:-999}
        ATTRS = {}
        ATTRSRAIN = {'day_0_rain':0,'day_1_rain':0,'day_2_rain':0,'day_3_rain':0,'day_4_rain':0,'day_5_rain':0}
        ATTRMIN = {}
        ATTRMAX = {}
        TOTAL = {0:0,1:0,2:0,3:0,4:0,5:0}
        cumulative = 0
        for rest in self._weather:

            data = json.loads(rest.data)
            localtimezone = pytz.timezone(data["timezone"])

            current = data["current"]
            if 'dt' in current:
                dt = current["dt"]
                formatted_dt = datetime.utcfromtimestamp(dt).replace(tzinfo=timezone.utc).astimezone(tz=None).strftime('%Y-%m-%d %H:%M:%S')
                ATTRS ["As at"] = formatted_dt
#                _LOGGER.warning("AS AT %s",formatted_dt)

            hourly = data["hourly"]
            for hour in hourly:

                # now determine the local day the last 24hrs = 0 24-48 = 1...
                localday = datetime.utcfromtimestamp(hour["dt"]).replace(tzinfo=timezone.utc).astimezone(tz=localtimezone)
                localnow = datetime.now(localtimezone)
                localdaynum = (localnow - localday).days

                if localdaynum >= len(self._daymax):
                    continue

                if 'rain' in hour:
                    rain = hour["rain"]
                    if not math.isnan(rain["1h"]):
                        TOTAL[localdaynum] += rain["1h"]
                        ATTRSRAIN ["day_%d_rain"%(localdaynum)] = round(TOTAL[localdaynum],2)

                if 'temp' in hour:
                    if hour["temp"] < MINTEMP[localdaynum]:
                        MINTEMP[localdaynum] = hour["temp"]
                        ATTRMIN["day_%d_min"%(localdaynum)] = hour["temp"]
                    if hour["temp"] > MAXTEMP[localdaynum]:
                        MAXTEMP[localdaynum] = hour["temp"]
                        ATTRMAX["day_%d_max"%(localdaynum)] = hour["temp"]
            
            #end hour loop

        #end rest loop
        
        #now loop through the data to calculate the adjustment factor
        for x in range(len(self._daymax)):
            
            cumulative += ATTRSRAIN ["day_%d_rain"%(x)]
            try:
                dayfac = 1 - ( cumulative - self._daymin[x])/(self._daymax[x]-self._daymin[x])
                if dayfac < minfac:
                    minfac = dayfac
            except:
                dayfac = 1
        
        if minfac < 0:
            minfac = 0

        self.factor = round(minfac,2)
#        self.attrs = {**ATTRS, **ATTRSRAIN, **ATTRMIN, **ATTRMAX}
        self.attrs = {**ATTRSRAIN, **ATTRMIN, **ATTRMAX}
