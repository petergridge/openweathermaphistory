"""Define the weather class."""

from datetime import date, datetime, timedelta
import json
import logging
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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

# from homeassistant.helpers import config_validation as cv, storage as store
from .const import (
    CONF_INTIAL_DAYS,
    CONF_MAX_CALLS,
    CONF_MAX_DAYS,
    CONST_API_AGGREGATE,
    CONST_API_CALL,
    CONST_API_CURRENT,
    CONST_API_FORECAST,
    CONST_API_OVERVIEW,
    CONST_CALLS,
    CONST_DAILY_RECORDS,
    CONST_HOURLY_RECORDS,
    CONST_INITIAL,
    DOMAIN,
)
from .data import RestData

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "OpenWeatherMap History"


class WeatherCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator for shared weather updates."""

    def __init__(self, hass: HomeAssistant, weather: Weather) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=10),
        )
        self._weather = weather

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        await self._weather.async_update()
        return self._weather


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

    @staticmethod
    def _precipitation_amount(value):
        """Return the precipitation amount from an API value."""
        if isinstance(value, dict):
            return next(iter(value.values()), 0)
        return value or 0

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

        if data is None or data == {}:
            _LOGGER.warning("OpenWeatherMap call failed, no data returned")
            return {}

        try:
            jdata = json.loads(data)
        except TypeError:
            _LOGGER.warning("OpenWeatherMap call failed, invalid json format, %s", data)
            return {}
        try:
            code = jdata["cod"]
            message = jdata["message"]
            _LOGGER.warning("OpenWeatherMap call failed code: %s: %s", code, message)
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
            _LOGGER.debug("OpenWeatherMap API call succeeded")

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
            first_timestamp = last_data_point + 3600
            count = min(
                CONST_HOURLY_RECORDS,
                (target - last_data_point) // 3600,
            )
            hourdata = await self.gethourdata_range(first_timestamp, count)
            if not hourdata:
                break
            data.update(hourdata)
            last_data_point = max(int(timestamp) for timestamp in hourdata)
        # end rest loop
        return data

    async def get_aggregatedata(self, aggregate, dates, historydata=None):
        """Fetch missing daily data in API-sized batches."""
        missing_dates = set(dates) - aggregate.keys()
        if not missing_dates:
            return aggregate

        oldest_date = min(missing_dates)
        day_start = datetime.strptime(oldest_date, "%Y-%m-%d").replace(
            tzinfo=ZoneInfo(self._timezone)
        )
        start = int(day_start.timestamp())
        remaining_dates = set(missing_dates)
        url = CONST_API_AGGREGATE % (
            self._lat,
            self._lon,
            start,
            min(CONST_DAILY_RECORDS, len(remaining_dates)),
            self._key,
        )
        while remaining_dates and self.remaining_calls() > 0:
            result = await self.get_rest(url)
            daily = result.get("data", []) if result else []
            if not daily:
                break

            previous_remaining = len(remaining_dates)
            for data in daily:
                timestamp = data.get("dt")
                if timestamp is None:
                    continue
                day = datetime.fromtimestamp(
                    int(timestamp), tz=ZoneInfo(self._timezone)
                ).strftime("%Y-%m-%d")
                if day not in remaining_dates:
                    continue
                temperature = data.get("temp", {})
                precipitation = self._precipitation_amount(
                    data.get("precipitation", data.get("rain", 0))
                )
                if historydata:
                    precipitation = sum(
                        hour_data.get("rain", 0) + hour_data.get("snow", 0)
                        for history_timestamp, hour_data in historydata.items()
                        if datetime.fromtimestamp(
                            int(history_timestamp), tz=ZoneInfo(self._timezone)
                        ).strftime("%Y-%m-%d")
                        == day
                    )
                aggregate[day] = {
                    "date": day,
                    "precipitation": precipitation,
                    "min_temp": temperature.get("min", 0),
                    "max_temp": temperature.get("max", 0),
                    "humidity": data.get("humidity", 0),
                    "pressure": data.get("pressure", 0),
                }
                remaining_dates.discard(day)

            next_url = result.get("next")
            if (
                not remaining_dates
                or not next_url
                or len(remaining_dates) == previous_remaining
            ):
                break
            url = next_url

        if remaining_dates and self.remaining_calls() < 1:
            self.call_limit_warning()
        return aggregate

    async def get_forecastdata(self):
        """Get forecast data."""
        # do not process when no calls remaining
        if self.remaining_calls() < 2:
            # only issue a single warning each day
            self.call_limit_warning()
            return {}

        current_url = (
            f"{CONST_API_CURRENT}?lat={self._lat}&lon={self._lon}"
            f"&units=metric&appid={self._key}"
        )
        current_result = await self.get_rest(current_url)
        current_data = current_result.get("data", []) if current_result else []
        if not current_data:
            return {}

        current = current_data[0]
        now = datetime.now(ZoneInfo(self._timezone))
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        url = CONST_API_FORECAST % (
            self._lat,
            self._lon,
            int(day_start.timestamp()),
            CONST_DAILY_RECORDS,
            self._key,
        )
        result = await self.get_rest(url)
        days = result.get("data", []) if result else []
        weather = current.get("weather", [])
        description = " ".join(
            instance.get("description", "") for instance in weather
        )

        # current observations
        currentdata = {
            "rain": self._precipitation_amount(current.get("rain", {})),
            "snow": self._precipitation_amount(current.get("snow", {})),
            "temp": current.get("temp", 0),
            "humidity": current.get("humidity", 0),
            "pressure": current.get("pressure", 0),
            "wind_speed": current.get("wind_speed", 0),
            "wind_deg": current.get("wind_deg", 0),
            "uvi": current.get("uvi", 0),
            "clouds": current.get("clouds", 0),
            "dew_point": current.get("dew_point", 0),
            "description": description,
        }
        # build forecast
        forecastdaily = {}
        for day in days:
            temp = day.get("temp", {})
            weather = day.get("weather")
            description = ""
            if weather:
                for instance in weather:
                    description += instance.get("description", "")
            daydata = {
                "max_temp": temp.get("max", 0),
                "min_temp": temp.get("min", 0),
                "pressure": day.get("pressure", 0),
                "humidity": day.get("humidity", 0),
                "pop": day.get("pop", 0),
                "rain": self._precipitation_amount(day.get("rain", 0)),
                "snow": self._precipitation_amount(day.get("snow", 0)),
                "wind_speed": day.get("wind_speed", 0),
                "wind_deg": day.get("wind_deg", 0),
                "uvi": day.get("uvi", 0),
                "clouds": day.get("clouds", 0),
                "description": description,
            }
            if timestamp := day.get("dt"):
                forecastdaily.update({timestamp: daydata})

        return currentdata, forecastdaily

    async def processcurrent(self, current):
        """Process the currrent data."""
        return {
            "current": {
                "rain": current.get("rain", 0),
                "snow": current.get("snow", 0),
                "humidity": current.get("humidity", 0),
                "temp": current.get("temp", 0),
                "pressure": current.get("pressure", 0),
                "wind_speed": current.get("wind_speed", 0),
                "wind_deg": current.get("wind_deg", 0),
                "uvi": current.get("uvi", 0),
                "clouds": current.get("clouds", 0),
                "description": current.get("description", ""),
                "dew_point": current.get("dew_point", 0),

            }
        }

    async def processdailyforecast(self, dailydata):
        "Process daily forecast data."
        processed_data = {}
        for i, (timestamp, data) in enumerate(
            sorted(dailydata.items(), key=lambda item: int(item[0]))
        ):
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
            day.update({"wind_speed": data.get("wind_speed", 0)})
            day.update({"wind_deg": data.get("wind_deg", 0)})
            day.update({"uvi": data.get("uvi", 0)})
            day.update({"clouds": data.get("clouds", 0)})
            day.update({"description": data.get("description", "")})
            day.update(
                {
                    "datetime": datetime.fromtimestamp(
                        int(timestamp), tz=ZoneInfo(self._timezone)
                    ).isoformat()
                }
            )
            processed_data.update({f"f{i}": day})
        return processed_data

    def remove_past_forecasts(self, dailydata):
        """Remove forecasts from before the current local day."""
        timezone = ZoneInfo(self._timezone)
        today = datetime.now(timezone).date()
        return {
            timestamp: data
            for timestamp, data in dailydata.items()
            if datetime.fromtimestamp(int(timestamp), tz=timezone).date() >= today
        }

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
        # x = []
        # y = []
        time = []
        plotly_rain = []
        plotly_snow = []
        plotly_temp = []
        plotly_pressure = []
        plotly_clouds = []
        plotly_humidity = []
        plotly_wind_speed = []
        plotly_uvi = []

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

            time.append(localday.strftime("%Y-%m-%dT%H:%M"))
            plotly_rain.append(round(data["rain"], 2))
            plotly_snow.append(round(data["snow"], 2))
            plotly_temp.append(round(data["temp"], 2))
            plotly_pressure.append(round(data["pressure"], 2))
            plotly_clouds.append(round(data.get("clouds",0), 0))
            plotly_humidity.append(round(data.get("humidity",0), 2))
            plotly_wind_speed.append(round(data.get("wind_speed",0), 2))
            plotly_uvi.append(round(data.get("uvi",0), 0))

        # age out old data
        for hour in removehours:
            historydata.pop(hour)
        plotly = {
            "plotly_time": time,
            "plotly_rain": plotly_rain,
            "plotly_snow": plotly_snow,
            "plotly_temp": plotly_temp,
            "plotly_pressure": plotly_pressure,
            "plotly_clouds": plotly_clouds,
            "plotly_humidity": plotly_humidity,
            "plotly_wind_speed": plotly_wind_speed,
            "plotly_uvi": plotly_uvi,
        }
        return historydata, processed_data, plotly

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
                1,
                self._key,
            )
        elif api == "day_summary":
            today = datetime.today().strftime("%Y-%m-%d")
            day_start = datetime.strptime(today, "%Y-%m-%d").replace(
                tzinfo=ZoneInfo(self._timezone)
            )
            url = CONST_API_AGGREGATE % (
                self._lat,
                self._lon,
                int(day_start.timestamp()),
                1,
                self._key,
            )
        elif api == "forecast":
            day_start = datetime.now(ZoneInfo(self._timezone)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            url = CONST_API_FORECAST % (
                self._lat,
                self._lon,
                int(day_start.timestamp()),
                CONST_DAILY_RECORDS,
                self._key,
            )
        elif api == "overview":
            url = CONST_API_OVERVIEW % (self._lat, self._lon, self._key)
        else:
            raise ValueError(f"Unknown OpenWeatherMap API: {api}")

        result = await self.get_rest(url)

        card = "" + chr(10)
        card += "**API Call**" + chr(10)
        card += "```" + chr(10)
        card += url.replace(self._key, "[redacted]") + chr(10)
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
        storage_key = "OWMH_" + self._name
        storeddata = await self.async_get_stored_data(storage_key)
        historydata = storeddata.get("history", {})
        currentdata = storeddata.get("current", {})
        stored_dailydata = storeddata.get("dailyforecast", {})
        dailydata = self.remove_past_forecasts(stored_dailydata)
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
        aggregate_dates = []
        if self._processing_type == CONST_INITIAL:
            # on start up just get the latest hour

            if last_data_point is None:
                last_data_point = thishour - 3600
            historydata = await self.async_backload(historydata)
            aggregate_dates.append(datetime.now(ZoneInfo(self._timezone)).date())
        elif int(datetime.today().minute) > 5:
            historydata = await self.async_backload(historydata)
            for i in range(int(self._maxdays)):
                aggregate_dates.append(
                    datetime.now(ZoneInfo(self._timezone)).date()
                    - timedelta(days=i)
                )

        # empty file
        if last_data_point is None:
            last_data_point = thishour - 3600
        # get new data if required
        # delay the reading of the data by 5 min to support corrections. The Seckte (Germany) problem
        if last_data_point < thishour and int(datetime.today().minute) > 5:
            data = await self.get_forecastdata()
            if data is None or data == {}:
                # httpx request failed
                if dailydata != stored_dailydata:
                    storeddata["dailyforecast"] = dailydata
                    await self.async_store_data(storeddata, storage_key)
                return
            currentdata = data[0]
            if data[1]:
                dailydata = self.remove_past_forecasts(data[1])
            historydata = await self.get_data(historydata)
            if not aggregate_dates:
                aggregate_dates = [
                    datetime.now(ZoneInfo(self._timezone)).date()
                    - timedelta(days=i)
                    for i in range(int(self._maxdays))
                ]

        if aggregate_dates:
            aggregate_data = await self.get_aggregatedata(
                aggregate,
                [day.isoformat() for day in aggregate_dates],
                historydata,
            )

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
        plotly = {"plotly": data[2]}
        data = await self.processdailyaggregate(aggregate_data)
        aggregate_data = data[0]
        processed_aggregate = data[1]
        # build data to support template variables
        self._processed = {
            **processeddaily,
            **processedcurrent,
            **processedweather,
            **processed_aggregate,
            **plotly,
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
        await self.async_store_data(zone_data, storage_key)

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

        count = min(
            CONST_HOURLY_RECORDS,
            hours,
            int(self._backlog),
        )
        start = earliestdata - (count * 3600)
        hourdata = await self.gethourdata_range(start, count)
        data.update(hourdata)
        self._backlog = max(0, self._backlog - len(hourdata))

        return data

    async def gethourdata(self, timestamp):
        """Get one hours data."""
        data = await self.gethourdata_range(timestamp, 1)
        return data.get(str(timestamp), {})

    async def gethourdata_range(self, timestamp, count):
        """Get a range of hourly data in one API call."""
        # do not process when no calls remaining
        if self.remaining_calls() < 1:
            # only issue a single warning each day
            self.call_limit_warning()
            return {}

        url = CONST_API_CALL % (
            self._lat,
            self._lon,
            timestamp,
            min(count, CONST_HOURLY_RECORDS),
            self._key,
        )

        result = await self.get_rest(url)
        if not result:
            return {}

        hourly = {}
        end = timestamp + count * 3600
        for record in result.get("data", []):
            record_timestamp = int(record.get("dt", 0))
            if not timestamp <= record_timestamp < end:
                continue
            hourly[str(record_timestamp)] = {
                "rain": self._precipitation_amount(record.get("rain", {})),
                "snow": self._precipitation_amount(record.get("snow", {})),
                "temp": record.get("temp", 0),
                "humidity": record.get("humidity", 0),
                "pressure": record.get("pressure", 0),
                "wind_speed": record.get("wind_speed", 0),
                "wind_deg": record.get("wind_deg", 0),
                "uvi": record.get("uvi", 0),
                "clouds": record.get("clouds", 0),
            }
        return hourly
