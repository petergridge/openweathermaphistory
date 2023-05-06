"""define the weather class"""

from .data import RestData
from datetime import datetime, date, timezone
from os.path import exists , join
import logging
import pickle
import re
import json
import pytz
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    )
from .const import (
    CONST_API_CALL,
    CONST_API_FORECAST,
    CONF_MAX_DAYS,
    CONF_INTIAL_DAYS
    )

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Open Weather Map History"

class Weather():
    """weather class"""
    def __init__(
        self,
        hass: HomeAssistant,
        config,
    ) -> None:

        self._timezone     = hass.config.time_zone
        self._hass         = hass
        self._config       = config
        self._attrsrain    = {}
        self._attrssnow    = {}
        self._attrshum     = {}
        self._mintemp      = {}
        self._maxtemp      = {}
        self._yesterdays   = {}
        self._tomorrow     = {}
        self._day_after    = {}
        self._processed    = {}

        self._name      = config.get(CONF_NAME,DEFAULT_NAME)
        self._lat       = config.get(CONF_LATITUDE,hass.config.latitude)
        self._lon       = config.get(CONF_LONGITUDE,hass.config.longitude)
        self._key       = config[CONF_API_KEY]
        self._initdays  = config.get(CONF_INTIAL_DAYS)
        self._maxdays   = config.get(CONF_MAX_DAYS)

    def get_stored_data(self):
        """Return stored data."""
        file = join(self._hass.config.path(), self._name  + '.pickle')
        if not exists(file):
            return {}
        with open(file, 'rb') as myfile:
            content = pickle.load(myfile)
        myfile.close()
        return content

    def store_data(self, content):
        """Store uri timestamp to file."""

        keys = list(content.keys())
        keys.sort()
        sorted_dict = {i: content[i] for i in keys}

        file = join(self._hass.config.path(), self._name + '.pickle')
        with open(file, 'wb') as myfile:
            pickle.dump(sorted_dict, myfile, pickle.HIGHEST_PROTOCOL)
        myfile.close()

    def validate_data(self,data) -> bool:
        """check if the call was successful"""
        try:
            code    = data["cod"]
            message = data["message"]
            _LOGGER.error('OpenWeatherMap call failed code: %s message: %s', code, message)
            return None
        except KeyError:
            pass

    async def get_forecastdata(self):
        """get forecast data"""
        url = CONST_API_FORECAST % (self._lat,self._lon, self._key)
        rest = RestData()
        await rest.set_resource(self._hass, url)
        await rest.async_update(log_errors=False)
        data = json.loads(rest.data)
        #check if the call was successful
        try:
            days = data.get('daily',{})
            current = data.get('current',{})
        except KeyError:
            _LOGGER.error('OpenWeatherMap forecast call failed data: %s', data)
        #current observations
        currentdata = {"rain":current.get('rain',{}).get('1h',0)
                    , "snow":current.get('snow',{}).get('1h',0)
                    , "temp":current.get("temp",0)
                    , "humidity":current.get("humidity",0)
                    , "pressure":current.get("pressure",0)}
        #build forecast
        forecastdaily = {}
        for day in days:
            temp = day.get('temp',{})
            daydata = {'max_temp':temp.get('max',0),
                       'min_temp':temp.get('min',0),
                       'pressure':day.get('pressure',0),
                       'humidity':day.get('humidity',0),
                       'pop':day.get('pop',0),
                       'rain': day.get('rain',0),
                       'snow':day.get('snow',0)}
            forecastdaily.update({day.get('dt') : daydata})

        return currentdata, forecastdaily

    async def get_historydata(self,num_hours,historydata):
        """get history data"""
        i=0
        rest = RestData()
        hour = datetime(date.today().year, date.today().month, date.today().day,datetime.now().hour)
        expectedhour = int(datetime.timestamp(hour))
        try:
            lastdt = max(historydata)
        except ValueError:
            #backdate the required number of days
            lastdt = expectedhour - 3600*24*self._initdays
        #iterate until caught up to current hour
        while lastdt < expectedhour :
            #increment last date by an hour
            lastdt += 3600
            url = CONST_API_CALL % (self._lat,self._lon, lastdt, self._key)
            rest = RestData()
            await rest.set_resource(self._hass, url)
            await rest.async_update(log_errors=False)
            #limit the number of calls in a scan interval
            i += 1
            if i > num_hours:
                self.store_data(historydata)
                break
            data = json.loads(rest.data)
            #check if the call was successful
            self.validate_data(data)
            try:
                current = data.get('data')[0]
                if current is None:
                    current = {}
            except KeyError:
                _LOGGER.error('OpenWeatherMap history call failed data: %s', data)
            #build this hours data
            precipval = {}
            preciptypes = ['rain','snow']
            for preciptype in preciptypes:
                if preciptype in current:
                    #get the rain/snow eg 'rain': {'1h':0.89}
                    precip = current[preciptype]
                    #get the first key eg 1h, 3h
                    key = next(iter(precip))
                    #get the number component assuming only a singe digit
                    divby = float(re.search(r'\d+', key).group())
                    try:
                        volume = precip.get(key,0)/divby
                    except ZeroDivisionError:
                        volume = 0
                    precipval.update({preciptype:volume})

            rain = precipval.get('rain',0)
            snow = precipval.get('snow',0)
            hourdata = {"rain": rain
                        ,"snow":snow
                        ,"temp":current.get("temp",0)
                        ,"humidity":current.get("humidity",0)
                        ,"pressure":current.get("pressure",0)}
            wdt = current["dt"]
            historydata.update({wdt : hourdata })
        #end rest loop
        return historydata

    async def processcurrent(self,current):
        """process the currrent data"""
        current_data ={ 'current': {'rain': current.get('rain')
                                   , 'snow': current.get('snow')
                                   , 'humidity': current.get('humidity')
                                   , 'temp': current.get('temp')
                                   , 'pressure': current.get('pressure')}
                                   }
        return current_data

    async def processdailyforecast(self,dailydata):
        "process daily forecast data"
        processed_data = {}
        i = 0
        for data in dailydata.values():
            #get the days data
            day = {}
            #update the days data
            day.update({"pop":data.get('pop',0)})
            day.update({"rain":data.get('rain',0)})
            day.update({"snow":data.get('snow',0)})
            day.update({"min_temp":data.get('min_temp',0)})
            day.update({"max_temp":data.get('max_temp',0)})
            day.update({"humidity":data.get('humidity',0)})
            day.update({"pressure":data.get('pressure',0)})
            processed_data.update({f'f{i}':day})
            i += 1
        return processed_data

    async def processhistory(self,historydata):
        """process history data"""
        removehours = []
        localtimezone = pytz.timezone(self._timezone)
        processed_data = {}
        for hour, data in historydata.items():
            localday = datetime.utcfromtimestamp(hour).replace(tzinfo=timezone.utc).astimezone(tz=localtimezone)
            localnow = datetime.now(localtimezone)
            localdaynum = (localnow - localday).days
            if localdaynum > self._maxdays-1:
                #identify data to age out
                removehours.append(hour)
                continue
            #get the days data
            day = processed_data.get(localdaynum,{})
            #process the new data
            rain = day.get('rain',0) + data["rain"]
            snow = day.get('snow',0) + data["snow"]
            mintemp = min(data["temp"],day.get('min_temp',999), 999)
            maxtemp = max(data["temp"],day.get('max_temp',-999), -999)
            #update the days data
            day.update({"rain":rain})
            day.update({"snow":snow})
            day.update({"min_temp":mintemp})
            day.update({"max_temp":maxtemp})
            processed_data.update({localdaynum:day})
        #age out old data
        for hour in removehours:
            historydata.pop(hour)
        return historydata,processed_data

    async def async_update(self,num_hours):
        '''update the weather stats'''
        hour = datetime(date.today().year, date.today().month, date.today().day,datetime.now().hour)
        expectedhour = int(datetime.timestamp(hour))
        #restore saved data
        storeddata = self.get_stored_data()
        historydata = storeddata.get("history",{})
        currentdata = storeddata.get('current',{})
        dailydata = storeddata.get('dailyforecast',{})
        #determine when the last update was done
        try:
            lastdt = max(historydata)
        except ValueError:
            #backdate the required number of days
            lastdt = expectedhour - 3600*24*self._initdays
        #get new data if requrired
        if lastdt < expectedhour:
            data = await self.get_forecastdata()
            currentdata = data[0]
            dailydata = data[1]
            historydata = await self.get_historydata(num_hours,historydata)
        #Process the available data
        processedcurrent = await self.processcurrent(currentdata)
        processeddaily = await  self.processdailyforecast(dailydata)
        data = await self.processhistory(historydata)
        historydata = data[0]
        processedweather = data[1]
        #build data to support template variables
        self._processed = {**processeddaily, **processedcurrent, **processedweather}
        #write persistent data
        self.store_data({'history':historydata, 'current':currentdata, 'dailyforecast':dailydata})
#        _LOGGER.warning(self._processed)

    def num_days(self) -> int:
        """ return how many days of data has been collected"""
        return len(self._attrsrain)

    def processed_value(self, period, value) -> float:
        """return the days current rainfall"""
        data = self._processed.get(period,{})
        return data.get(value,0)

