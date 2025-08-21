"""Define the weather class."""

from datetime import date, datetime, timedelta
import json
import logging
import re
from zoneinfo import ZoneInfo

from homeassistant.components.persistent_notification import async_create, async_dismiss
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import storage as store

# from homeassistant.helpers import config_validation as cv, storage as store
from .const import (
    CONF_INTIAL_DAYS,
    CONF_MAX_CALLS,
    CONF_MAX_DAYS,
    CONST_API_AGGREGATE,
    CONST_API_CALL,
    CONST_API_FORECAST,
    CONST_API_OVERVIEW,
    CONST_CALLS,
    CONST_INITIAL,
)
from .data import RestData

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "OpenWeatherMap History"


class Weather:
    """weather class."""

    def __init__(  # noqa: D107
        self,
        hass: HomeAssistant,
        config,
    ) -> None:
        self._timezone = hass.config.time_zone
        self._hass = hass
        self._config = config
        self._processed = {}

        self._num_days = 0
        self._name = config.get(CONF_NAME, DEFAULT_NAME)
        self._lat = config[CONF_LOCATION].get(CONF_LATITUDE, hass.config.latitude)
        self._lon = config[CONF_LOCATION].get(CONF_LONGITUDE, hass.config.longitude)
        self._key = config[CONF_API_KEY]
        self._initdays = config.get(CONF_INTIAL_DAYS, 5)
        self._maxdays = config.get(CONF_MAX_DAYS, 5)
        self._maxcalls = config.get(CONF_MAX_CALLS, 1000)
        self._backlog = 0
        self._processing_type = None
        self._daily_count = 1
        self._warning_issued = False

    async def async_get_stored_data(self, key):
        """Get data from .storage."""
        data = {}
        x = store.Store[dict[any]](self._hass, 1, key)
        data = await x.async_load()
        if data is None:
            data = {}
        return data

    async def async_store_data(self, content, key):
        """Put data into .storage."""
        x = store.Store[dict[any]](self._hass, 1, key)
        await x.async_save(content)

    def remaining_backlog(self):
        "Return remaining days to collect."
        return self._backlog

    def remaining_calls(self):
        """Return remaining call count."""
        return self._maxcalls - self._daily_count

    def call_limit_warning(self):
        """Issue a warning when the call limit is exceeded."""
        if not self._warning_issued:
            _LOGGER.warning("Maximum daily allowance of API calls have been used")
            self._warning_issued = True

    def validate_data(self, data) -> bool:
        """Check if the call was successful."""

        if data is None:
            _LOGGER.error("OpenWeatherMap call failed, no data returned")
            return {}

        try:
            jdata = json.loads(data)
        except TypeError:
            _LOGGER.error("OpenWeatherMap call failed, invalid json format")
            return {}

        try:
            code = jdata["cod"]
            message = jdata["message"]
            _LOGGER.error("OpenWeatherMap call failed code: %s: %s", code, message)
        except KeyError:
            return jdata
            # return {}
        else:
            return {}

    async def get_rest(self, url):
        """Get the data from the WWW."""
        rest = RestData()
        await rest.set_resource(self._hass, url)
        await rest.async_update(log_errors=False)
        result = self.validate_data(rest.data)
        if result:
            _LOGGER.debug(url)
            _LOGGER.debug(result)

        self._daily_count += 1
        return result

    async def get_data(self, historydata):
        """Get data from the newest timestamp forward."""
        hour = datetime(
            date.today().year, date.today().month, date.today().day, datetime.now().hour
        )
        thishour = int(datetime.timestamp(hour))
        data = historydata
        # on startup only get one hour of data to not impact HA start
        if self._processing_type == CONST_INITIAL:
            hours = 1
        else:
            hours = CONST_CALLS

        last_data_point = self.maxdict(data)
        if last_data_point is None:
            # no data yet just get this hours dataset
            last_data_point = thishour - 3600
        # iterate until caught up to current hour
        # or exceeded the call limit
        target = min(thishour, last_data_point + hours * 3600)
        while last_data_point < target:
            # increment last date by an hour
            last_data_point += 3600
            hourdata = await self.gethourdata(last_data_point)
            if hourdata == {}:
                break
            data.update({last_data_point: hourdata})
        # end rest loop
        return data

    async def get_aggregatedata(self, aggregate, indate=None):
        """Get aggregate day data."""
        # not implemented
        # do not process when no calls remaining
        if self.remaining_calls() < 1:
            # only issue a single warning each day
            self.call_limit_warning()
            return {}
        today = datetime.today().strftime("%Y-%m-%d")
        if indate:
            today = indate

        url = CONST_API_AGGREGATE % (self._lat, self._lon, today, self._key)
        result = await self.get_rest(url)

        if result:
            day = {}
            # update the days data
            day.update({"date": result.get("date")})
            day.update({"precipitation": result.get("precipitation").get("total", 0)})
            day.update({"min_temp": result.get("temperature").get("min", 0)})
            day.update({"max_temp": result.get("temperature").get("max", 0)})
            day.update({"humidity": result.get("humidity").get("afternoon", 0)})
            day.update({"pressure": result.get("pressure").get("afternoon", 0)})
            aggregate[result.get("date")] = day

        return aggregate

    async def get_forecastdata(self):
        """Get forecast data."""
        # do not process when no calls remaining
        if self.remaining_calls() < 1:
            # only issue a single warning each day
            self.call_limit_warning()
            return {}

        url = CONST_API_FORECAST % (self._lat, self._lon, self._key)
        result = await self.get_rest(url)
        days = {}
        current = {}
        if result:
            days = result.get("daily")
            current = result.get("current")

        # current observations
        currentdata = {
            "rain": current.get("rain", {}).get("1h", 0),
            "snow": current.get("snow", {}).get("1h", 0),
            "temp": current.get("temp", 0),
            "humidity": current.get("humidity", 0),
            "pressure": current.get("pressure", 0),
        }
        # build forecast
        forecastdaily = {}
        for day in days:
            temp = day.get("temp", {})
            daydata = {
                "max_temp": temp.get("max", 0),
                "min_temp": temp.get("min", 0),
                "pressure": day.get("pressure", 0),
                "humidity": day.get("humidity", 0),
                "pop": day.get("pop", 0),
                "rain": day.get("rain", 0),
                "snow": day.get("snow", 0),
            }
            forecastdaily.update({day.get("dt"): daydata})

        return currentdata, forecastdaily

    async def processcurrent(self, current):
        """Process the currrent data."""
        return {
            "current": {
                "rain": current.get("rain"),
                "snow": current.get("snow"),
                "humidity": current.get("humidity"),
                "temp": current.get("temp"),
                "pressure": current.get("pressure"),
            }
        }

    async def processdailyforecast(self, dailydata):
        "Process daily forecast data."
        processed_data = {}
        for i, data in enumerate(dailydata.values()):
            # get the days data
            day = {}
            # update the days data
            day.update({"pop": data.get("pop", 0)})
            day.update({"rain": data.get("rain", 0)})
            day.update({"snow": data.get("snow", 0)})
            day.update({"min_temp": data.get("min_temp", 0)})
            day.update({"max_temp": data.get("max_temp", 0)})
            day.update({"humidity": data.get("humidity", 0)})
            day.update({"pressure": data.get("pressure", 0)})
            processed_data.update({f"f{i}": day})
        return processed_data

    async def processdailyaggregate(self, aggregatedata):
        "Process daily aggregate data."
        # remove excess aggregate data (more than specified days)
        sorteddata = sorted(
            aggregatedata.items(),
            reverse=True,
            key=lambda x: datetime.strptime(x[0], "%Y-%m-%d"),
        )
        for i, values in enumerate(sorteddata):
            val = list(values)[0]
            if i > self._maxdays - 1:
                aggregatedata.pop(val)
        processed_data = {}
        for i, values in enumerate(sorteddata):
            # if day is earlier than n days ago
            day = {}
            data = values[1]
            day.update({"date": data.get("date")})
            day.update({"precipitation": data.get("precipitation")})
            day.update({"min_temp": data.get("min_temp")})
            day.update({"max_temp": data.get("max_temp")})
            day.update({"humidity": data.get("humidity")})
            day.update({"pressure": data.get("pressure")})

            processed_data.update({f"a{i}": day})
        return aggregatedata, processed_data

    async def processhistory(self, historydata):
        """Process history data."""
        removehours = []
        processed_data = {}
        day = {}
        x = []
        y = []

        for hour, data in sorted(
            historydata.items(), key=lambda x: int(x[0])
        ):  # sorted by hour
            localday = datetime.fromtimestamp(int(hour), tz=ZoneInfo(self._timezone))
            localnow = datetime.now(ZoneInfo(self._timezone))
            localdaynum = (localnow - localday).days

            self._num_days = max(self._num_days, localdaynum)
            if localdaynum > self._maxdays - 1:
                # identify data to age out
                removehours.append(hour)
                continue
            # get the days data
            day = processed_data.get(localdaynum, {})

            # process the new data
            rain = day.get("rain", 0) + data["rain"]
            snow = day.get("snow", 0) + data["snow"]
            mintemp = min(data["temp"], day.get("min_temp", 999), 999)
            maxtemp = max(data["temp"], day.get("max_temp", -999), -999)
            # update the days data
            day.update({"rain": round(rain, 2)})
            day.update({"snow": snow})
            day.update({"min_temp": mintemp})
            day.update({"max_temp": maxtemp})
            processed_data.update({localdaynum: day})

            x.append(localday.strftime("%Y-%m-%dT%H:%M"))
            y.append(round(data["rain"], 2))

        # age out old data
        for hour in removehours:
            historydata.pop(hour)

        return historydata, processed_data, {"x": x, "y": y}

    def set_processing_type(self, option):
        """Allow setting of the processing type."""
        self._processing_type = option

    def get_processing_type(self):
        """Allow setting of the processing type."""
        return self._processing_type

    def num_days(self) -> int:
        """Return how many days of data has been collected."""
        return self._num_days

    def max_days(self) -> int:
        """Return how many days of data has been collected."""
        return self._maxdays

    def daily_count(self) -> int:
        """Return daily of data has been collected."""
        return self._daily_count

    def processed_value(self, period, value) -> float:
        """Return data has been collected."""
        data = self._processed.get(period, {})
        return data.get(value, 0)

    async def show_call_data(self, api):
        """Call the api and show the result."""
        if api == "timemachine":
            hour = datetime(
                date.today().year,
                date.today().month,
                date.today().day,
                datetime.now().hour,
            )
            thishour = int(datetime.timestamp(hour))
            url = CONST_API_CALL % (
                self._lat,
                self._lon,
                thishour,
                self._key,
            )  # self._key
        elif api == "day_summary":
            today = datetime.today().strftime("%Y-%m-%d")
            url = CONST_API_AGGREGATE % (self._lat, self._lon, today, self._key)
        elif api == "forecast":
            url = CONST_API_FORECAST % (self._lat, self._lon, self._key)
        elif api == "overview":
            url = CONST_API_OVERVIEW % (self._lat, self._lon, self._key)

        result = await self.get_rest(url)

        card = "" + chr(10)
        card += "**API Call**" + chr(10)
        card += "```" + chr(10)
        card += url + chr(10)
        card += "```" + chr(10)
        card += "**API Response**" + chr(10)
        card += "```" + chr(10)
        # format the json for output
        card += json.dumps(result, indent=4) + chr(10)
        card += "```" + chr(10)

        async_dismiss(self._hass, "owmhshowcall")
        async_create(
            self._hass,
            message=card,
            title="OWMH API Response",
            notification_id="owmhshowcall",
        )

    async def async_update(self):
        """Update the weather stats."""

        hour = datetime(
            date.today().year, date.today().month, date.today().day, datetime.now().hour
        )
        thishour = int(datetime.timestamp(hour))
        day = datetime(date.today().year, date.today().month, date.today().day)
        # GMT midnight
        midnight = int(datetime.timestamp(day))
        # restore saved data
        storeddata = await self.async_get_stored_data("OWMH_" + self._name)
        historydata = storeddata.get("history", {})
        currentdata = storeddata.get("current", {})
        dailydata = storeddata.get("dailyforecast", {})
        aggregate = storeddata.get("aggregate", {})
        dailycalls = storeddata.get("dailycalls", {})
        self._daily_count = dailycalls.get("count", 0)
        # reset the daily count on new UTC day
        if dailycalls.get("time", 0) < midnight:
            self._daily_count = 1
            self._warning_issued = False
        aggregate_data = aggregate
        dailycalls = {"time": midnight, "count": self._daily_count}
        last_data_point = self.maxdict(historydata)
        if self._processing_type == CONST_INITIAL:
            # on start up just get the latest hour

            if last_data_point is None:
                last_data_point = thishour - 3600
            historydata = await self.async_backload(historydata)
            aggregate_data = await self.get_aggregatedata(aggregate)
        elif int(datetime.today().minute) > 5:
            historydata = await self.async_backload(historydata)
            for i in range(int(self._maxdays)):
                today = (datetime.today() - timedelta(days=i)).strftime("%Y-%m-%d")
                if not aggregate_data.get(today):
                    aggregate_data = await self.get_aggregatedata(aggregate, today)

        # empty file
        if last_data_point is None:
            last_data_point = thishour - 3600
        # get new data if required
        # delay the reading of the data by 5 min to support corrections. The Seckte (Germany) problem
        if last_data_point < thishour and int(datetime.today().minute) > 5:
            data = await self.get_forecastdata()
            if data is None or data == {}:
                # httpx request failed
                return
            currentdata = data[0]
            dailydata = data[1]
            historydata = await self.get_data(historydata)
            aggregate_data = await self.get_aggregatedata(aggregate)

        # recaculate the backlog
        data = historydata
        hour = datetime(
            date.today().year, date.today().month, date.today().day, datetime.now().hour
        )
        thishour = int(datetime.timestamp(hour))
        if data == {}:
            earliestdata = thishour
        else:
            try:
                earliestdata = self.mindict(data)
            except ValueError:
                earliestdata = thishour

        self._backlog = max(
            0, ((self._initdays * 24 * 3600) - (thishour - earliestdata)) / 3600
        )
        # Process the available data
        processedcurrent = await self.processcurrent(currentdata)
        processeddaily = await self.processdailyforecast(dailydata)
        data = await self.processhistory(historydata)
        historydata = data[0]
        processedweather = data[1]
        plotty = {"plotty": data[2]}
        data = await self.processdailyaggregate(aggregate_data)
        aggregate_data = data[0]
        processed_aggregate = data[1]
        # build data to support template variables
        self._processed = {
            **processeddaily,
            **processedcurrent,
            **processedweather,
            **processed_aggregate,
            **plotty,
        }

        dailycalls = {
            "time": midnight,
            "count": self._daily_count,
            "lat": self._lat,
            "lon": self._lon,
        }

        zone_data = {
            "history": historydata,
            "current": currentdata,
            "dailyforecast": dailydata,
            "aggregate": aggregate_data,
            "dailycalls": dailycalls,
        }
        await self.async_store_data(zone_data, "OWMH_" + self._name)

    def mindict(self, data):
        """Find minimum dictionary key."""
        if data == {}:
            return None
        mini = int(next(iter(data)))
        for x in data:
            mini = min(int(x), mini)
        return mini

    def maxdict(self, data):
        """Find minimum dictionary key."""
        if data == {}:
            return None
        maxi = int(next(iter(data)))
        for x in data:
            maxi = max(int(x), maxi)
        return maxi

    async def async_backload(self, historydata):
        """Backload data."""
        # from the oldest recieved data backward
        # until all the backlog is processed
        data = historydata
        hour = datetime(
            date.today().year, date.today().month, date.today().day, datetime.now().hour
        )
        thishour = int(datetime.timestamp(hour))
        # limit the number of API calls in a single execution
        if self._processing_type == CONST_INITIAL:
            hours = 1
        else:
            hours = CONST_CALLS

        if data == {}:  # new location
            # the oldest data collected so far
            earliestdata = thishour
        else:
            try:
                earliestdata = self.mindict(data)
            except ValueError:
                earliestdata = thishour

        expected_earliest_data = thishour - (self._initdays * 24 * 3600)
        backlog = earliestdata - expected_earliest_data - 3600
        self._backlog = max(0, backlog / 3600)
        if self._backlog < 1:
            return data

        x = 1
        while x <= hours:
            # get the data for the hour
            data_point_time = earliestdata - (3600 * x)
            hourdata = await self.gethourdata(data_point_time)
            if hourdata == {}:
                # no data found so abort the loop
                break
            # Add the data collected oected to the weather history
            data.update({str(data_point_time): hourdata})
            # decrement the backlog
            self._backlog -= 1
            if self._backlog < 1:
                break
            x += 1

        return data

    async def gethourdata(self, timestamp):
        """Get one hours data."""
        # do not process when no calls remaining
        if self.remaining_calls() < 1:
            # only issue a single warning each day
            self.call_limit_warning()
            return {}

        url = CONST_API_CALL % (self._lat, self._lon, timestamp, self._key)

        result = await self.get_rest(url)
        if result:
            current = result.get("data")[0]
            if current is None:
                current = {}
        else:
            return {}

        # build this hours data
        precipval = {}
        preciptypes = ["rain", "snow"]
        for preciptype in preciptypes:
            if preciptype in current:
                # get the rain/snow eg 'rain': {'1h':0.89}
                precip = current[preciptype]
                # get the first key eg 1h, 3h
                key = next(iter(precip))
                # get the number component assuming only a singe digit
                divby = float(re.search(r"\d+", key).group())
                try:
                    volume = precip.get(key, 0) / divby
                except ZeroDivisionError:
                    volume = 0
                precipval.update({preciptype: volume})

        rain = precipval.get("rain", 0)
        snow = precipval.get("snow", 0)
        return {
            "rain": rain,
            "snow": snow,
            "temp": current.get("temp", 0),
            "humidity": current.get("humidity", 0),
            "pressure": current.get("pressure", 0),
        }
