"""Process the weater data"""

import logging
import json
import math
from datetime import datetime, timezone
import pytz
import pickle
from os.path import exists, join

_LOGGER = logging.getLogger(__name__)

class WeatherHist:
    """Class for handling the data retrieval."""

    def __init__(self):
        """Initialize the data object."""
        self._weather      = None
        self._daysig       = None
        self._water_target = None
        self.attrs         = None
        self.factor        = None
        self._units        = None
        self._timezone     = None
        self._hass         = None
        self._name         = None

    async def set_weather(self, weather, daysig, watertarget, units, time_zone, hass, name):
        """Set url."""
        self._weather      = weather
        self._daysig       = daysig
        self._water_target = watertarget
        self._units        = units
        self._timezone     = time_zone
        self._hass         = hass
        self._name         = name

    def get_stored_data(self,):
        """Return stored data."""
        file = join(self._hass.config.path(), self._name + '.pickle')
        if not exists(file):
            return {}
        with open(file, 'rb') as myfile:
            content = pickle.load(myfile)
        myfile.close()
        return content

    def store_data(self, content):
        """Store uri timestamp to file."""
        file = join(self._hass.config.path(), self._name + '.pickle')
        with open(file, 'wb') as myfile:
            pickle.dump(content, myfile, pickle.HIGHEST_PROTOCOL)
        myfile.close()

    async def async_update(self):
        '''update the weather stats'''
        factor = 1
        mintemp = {0:999,1:999,2:999,3:999,4:999}
        maxtemp = {0:-999,1:-999,2:-999,3:-999,4:-999}
        attrsrain = {'day_0_rain':0,'day_1_rain':0,'day_2_rain':0,'day_3_rain':0,'day_4_rain':0}
        attrssnow = {'day_0_snow':0,'day_1_snow':0,'day_2_snow':0,'day_3_snow':0,'day_4_snow':0}
        attrmin = {}
        attrmax = {}
        totalrain = {0:0,1:0,2:0,3:0,4:0}
        totalsnow = {0:0,1:0,2:0,3:0,4:0}

        #get persistent data to limit the number of calls on restart
        weatherdata = self.get_stored_data()
        localtimezone =   pytz.timezone(self._timezone)

        for rest in self._weather:
            data = json.loads(rest.data)

            #check if the call was successful
            try:
                code    = data["cod"]
                message = data["message"]
                _LOGGER.error('OpenWeatherMap call failed code: %s message: %s', code, message)
                return #just stop processing
            except KeyError:
                pass
            #get the data
            try:
                current = data["data"][0]
            except KeyError:
                _LOGGER.error('OpenWeatherMap call failed data: %s', data)
                return #just stop processing
            #build this hours data
            rainval = 0
            if 'rain' in current:
                rain = current["rain"]
                if not math.isnan(rain["1h"]):
                    rainval = rain["1h"]
            snowval = 0
            if 'snow' in current:
                snow = current["snow"]
                if not math.isnan(snow["1h"]):
                    snowval = snow["1h"]
            tempval = current["temp"]
            hourdata = {"rain":rainval, "snow":snowval, "temp":tempval}
            dt = current["dt"]
            weatherdata.update({dt : hourdata })
        #end rest loop

        removehours = []
        #now reprocess the data to calc each days data
        for hour, data in weatherdata.items():
            localday = datetime.utcfromtimestamp(hour).replace(tzinfo=timezone.utc).astimezone(tz=localtimezone)
            localnow = datetime.now(localtimezone)
            localdaynum = (localnow - localday).days
            if localdaynum > 4:
                removehours.append(hour)
                continue

            totalrain.update({localdaynum: totalrain[localdaynum] + data["rain"]})
            totalsnow.update({localdaynum: totalsnow[localdaynum] + data["snow"]})
            if self._units == "imperial":
                #convert to inches
                attrsrain.update({"day_%d_rain"%(localdaynum) : round(totalrain[localdaynum]/25.4,2)})
                attrssnow.update({"day_%d_snow"%(localdaynum) : round(totalsnow[localdaynum]/25.4,2)})
            else:
                attrsrain.update({"day_%d_rain"%(localdaynum) : round(totalrain[localdaynum],2)})
                attrssnow.update({"day_%d_snow"%(localdaynum) : round(totalsnow[localdaynum],2)})

            if data["temp"] < mintemp[localdaynum]:
                mintemp.update({localdaynum : data["temp"]})
                attrmin.update({"day_%d_min"%(localdaynum): data["temp"]})
            if data["temp"] > maxtemp[localdaynum]:
                maxtemp.update({localdaynum : data["temp"]})
                attrmax.update({"day_%d_max"%(localdaynum): data["temp"]})

        #now loop through the data to calculate the adjustment factor
        equivalent = 0
        for day, daysig in enumerate(self._daysig):
            #calculate rainfall equivalent watering
            #each days rain has varying significance
            #e.g. yesterdays rain is less significant than todays rain
            equivalent += attrsrain ["day_%d_rain"%(day)] * daysig
        try:
            if equivalent < self._water_target:
                #calculate the factor
                factor = (self._water_target - equivalent) / self._water_target
                factor = max(0,factor)
            else:
                factor = 0
        except ZeroDivisionError:
            #watering target has been set as 0
            factor = 1

        self.factor = ('%.2f' %factor)
        self.attrs = {**attrsrain, **attrssnow, **attrmin, **attrmax}

        #clear old data
        for hour in removehours:
            weatherdata.pop(hour)
        _LOGGER.warning('Weaterdata item count: %s', len(weatherdata))
        #write persistent data
        self.store_data(weatherdata)