"""Support for RESTful API."""
import json
import logging
import math
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from json import JSONEncoder

import pytz
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import CONST_API_CALL_3, STORAGE_KEY, STORAGE_VERSION
from .data import RestData

_LOGGER = logging.getLogger(__name__)


@dataclass
class WeatherData:
    rain: float
    snow: float
    temp: float
    humidity: float


class WeatherEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, deque):
            return list(obj)
        elif isinstance(obj, WeatherData):
            return asdict(obj)
        elif isinstance(obj, datetime):
            return str(obj)
        return JSONEncoder.default(self, obj)


class WeatherHistoryV3:
    """Class for handling the weather data retrieval for the v 3.0 api."""

    def __init__(
        self,
        key: str,
        hass: HomeAssistant,
        lat: float,
        lon: float,
        units: str,
        url_template: str = CONST_API_CALL_3,
        lookback_days: int = 5,
    ):
        self._hourly_history: deque[tuple[datetime, WeatherData]] = deque(
            maxlen=lookback_days * 24
        )
        self._store = Store[dict[str, deque[tuple[datetime, WeatherData]]]](
            hass, STORAGE_VERSION, STORAGE_KEY, encoder=WeatherEncoder
        )

        self.lat = lat
        self.lon = lon
        self.hass = hass
        self.units = units
        self.lookback_days = lookback_days
        self._url_template = url_template
        self._key = key

    def _make_url(self, date: datetime):
        fmt_date = int(date.timestamp())
        return self._url_template % (
            self.lat,
            self.lon,
            fmt_date,
            self._key,
            self.units,
        )

    async def async_load(self):
        """Load data from persistent storage"""
        if (data := await self._store.async_load()) is None:
            _LOGGER.debug("No data from storage: %s", self._store.path)
            return

        self._hourly_history.clear()
        for dt_str, wd_dict in data["hourly_history"]:
            dt = datetime.fromisoformat(dt_str)
            wd = WeatherData(**wd_dict)
            self._hourly_history.append((dt, wd))

        _LOGGER.debug("Loaded data from storage: %s", self._hourly_history)

    async def async_save(self):
        _LOGGER.debug("Saving data to storage %s", self._hourly_history)
        await self._store.async_save({"hourly_history": self._hourly_history})

    async def backfill_update(self):
        """Backfill hourly data for self.lookback_days days.
        NOTE: This requires 1 api call per hour on v3 api."""

        # TODO: Can reduce api calls by up to 23 on a backfill by calling non-timemachine API
        # endpoint for most recent 24hrs.  timemachine endpoint now only returns 1 hour on v3

        end_dt = datetime.now(tz=timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )
        start_dt = end_dt - timedelta(days=self.lookback_days)

        _LOGGER.debug(
            "Backfilling weather data between %s and %s (%s)",
            start_dt,
            end_dt,
            start_dt <= end_dt,
        )

        dt_to_data = {d[0]: d[1] for d in self._hourly_history}

        self._hourly_history.clear()

        while start_dt <= end_dt:
            _LOGGER.debug("Backfilling weather data for %s", start_dt)
            if start_dt in dt_to_data:
                # If we already have the data, no need to request
                _LOGGER.debug("Found weather data for %s, skipping request", start_dt)
                self._hourly_history.appendleft((start_dt, dt_to_data[start_dt]))
            else:
                await self._async_update_for_date(start_dt)
            start_dt += timedelta(hours=1)

        await self.async_save()

    async def async_update(self) -> bool:
        """Get update for top of the current hour"""
        date = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
        result = await self._async_update_for_date(date)
        await self.async_save()
        return result

    async def _async_update_for_date(self, date: datetime) -> bool:
        _LOGGER.debug("Updating weather history for %s", date)

        if self._hourly_history and self._hourly_history[0][0] == date:
            _LOGGER.info("Already have observation for %s, skipping", date)
            return False

        url = self._make_url(date)
        data = RestData()
        await data.set_resource(self.hass, url)
        await data.async_update(log_errors=False)

        if data.data is None:
            _LOGGER.warning("Got no data for %s !", date)
            return False
        return self.add_observation(data)

    def add_observation(self, data: RestData) -> bool:
        json_data = data.data
        json_data = json_data["data"][0]

        dt = datetime.fromtimestamp(json_data["dt"], tz=timezone.utc)

        rain = json_data["rain"]["1h"] if "rain" in json_data else 0
        snow = json_data["snow"]["1h"] if "snow" in json_data else 0

        # Rain and snow data comes back in mm/h even if we specify imperial units in the url,
        # convert to in/h if needed
        if self.units == "imperial":
            rain /= 25.4
            snow /= 25.4

        wd = WeatherData(
            rain=rain,
            snow=snow,
            temp=json_data["temp"],
            humidity=json_data["humidity"],
        )

        if self._hourly_history:
            last_dt = self._hourly_history[0][0]
            if dt - last_dt > timedelta(hours=1):
                _LOGGER.warning(
                    "Missing observation.  Current dt: %s last dt: %s.\n Data: %s",
                    dt,
                    last_dt,
                    self._hourly_history,
                )

            elif last_dt == dt:
                _LOGGER.warning(
                    "Already seen observation for: %s, skipping.\n Data: %s"
                )
                return False

        _LOGGER.debug("Adding observation: %s, %s", dt, wd)
        self._hourly_history.appendleft((dt, wd))
        return True

    def day_rain(self, day: int) -> float:
        """Get total rain day.  day=0 returns the total in the last 24hrs,
        day=1 returns the total from 48hrs ago to 24hrs ago, etc."""
        return self._day_attr(day, "rain")

    def day_snow(self, day: int) -> float:
        """Get total snow for day.  day=0 returns the total in the last 24hrs,
        day=1 returns the total from 48hrs ago to 24hrs ago, etc."""
        return self._day_attr(day, "snow")

    def day_humidity(self, day: int) -> float:
        """Get average humidity for day.  day=0 returns the average in the last 24hrs,
        day=1 returns the average from 48hrs ago to 24hrs ago, etc."""
        return self._day_attr(day, "humidity")

    def day_temp_high(self, day: int) -> float:
        """Get high temp for day.  day=0 returns the value in the last 24hrs,
        day=1 returns the value from 48hrs ago to 24hrs ago, etc."""
        return self._day_attr(day, "temp_high")

    def day_temp_low(self, day: int) -> float:
        """Get low temp for day.  day=0 returns the value from the last 24hrs,
        day=1 returns the value from 48hrs ago to 24hrs ago, etc."""
        return self._day_attr(day, "temp_low")

    def _day_attr(self, day: int, attr: str) -> float:
        today = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
        end = today - timedelta(days=day)
        start = end - timedelta(days=1)
        total = 0.0
        high = -999.0
        low = 999.0
        count = 0

        ix = 0
        while end >= start:
            if len(self._hourly_history) > ix and self._hourly_history[ix][0] > end:
                ix += 1

            if len(self._hourly_history) > ix and self._hourly_history[ix][0] == end:
                match attr:
                    case "snow":
                        total += self._hourly_history[ix][1].snow
                    case "rain":
                        total += self._hourly_history[ix][1].rain
                    case "humidity":
                        total += self._hourly_history[ix][1].humidity
                        count += 1
                    case "temp_high":
                        if self._hourly_history[ix][1].temp > high:
                            high = self._hourly_history[ix][1].temp
                    case "temp_low":
                        if self._hourly_history[ix][1].temp < low:
                            low = self._hourly_history[ix][1].temp

            end -= timedelta(hours=1)

        match attr:
            case "humidity":
                if count == 0:
                    return 0
                return total / count
            case "temp_high":
                return high
            case "temp_low":
                return low
            case _:
                return total


class WeatherHist:
    """Class for handling the data retrieval."""

    def __init__(self):
        """Initialize the data object."""
        self._weather = None
        self._daysig = None
        self._water_target = None
        self.attrs = None
        self.factor = None
        self._units = None
        self._timezone = None

    async def set_weather(self, weather, daysig, watertarget, units, time_zone):
        """Set url."""
        self._weather = weather
        self._daysig = daysig
        self._water_target = watertarget
        self._units = units
        self._timezone = time_zone

    async def async_update(self):
        """update the weather stats"""
        _LOGGER.debug("Updating weatherhistory")
        factor = 1
        mintemp = {0: 999, 1: 999, 2: 999, 3: 999, 4: 999, 5: 999}
        maxtemp = {0: -999, 1: -999, 2: -999, 3: -999, 4: -999, 5: -999}
        attrs = {}
        attrsrain = {
            "day_0_rain": 0,
            "day_1_rain": 0,
            "day_2_rain": 0,
            "day_3_rain": 0,
            "day_4_rain": 0,
            "day_5_rain": 0,
        }
        attrssnow = {
            "day_0_snow": 0,
            "day_1_snow": 0,
            "day_2_snow": 0,
            "day_3_snow": 0,
            "day_4_snow": 0,
            "day_5_snow": 0,
        }
        attrmin = {}
        attrmax = {}
        totalrain = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        totalsnow = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        for rest in self._weather:
            data = json.loads(rest.data)
            try:
                localtimezone = pytz.timezone(data["timezone"])
            except KeyError:
                localtimezone = pytz.timezone(self._timezone)

            # check if the call was successful
            try:
                code = data["cod"]
                message = data["message"]
                _LOGGER.error(
                    "OpenWeatherMap call failed code: %s message: %s", code, message
                )
                return  # just stop processing
            except KeyError:
                pass
            # get the data
            try:
                current = data["current"]
            except KeyError:
                _LOGGER.error("OpenWeatherMap call failed data: %s", data)
                return  # just stop processing

            if "dt" in current:
                date = current["dt"]
                formatted_dt = (
                    datetime.utcfromtimestamp(date)
                    .replace(tzinfo=timezone.utc)
                    .astimezone(tz=None)
                    .strftime("%Y-%m-%d %H:%M:%S")
                )
                attrs["As at"] = formatted_dt

            hourly = data["hourly"]
            for hour in hourly:
                # now determine the local day the last 24hrs = 0 24-48 = 1...
                localday = (
                    datetime.utcfromtimestamp(hour["dt"])
                    .replace(tzinfo=timezone.utc)
                    .astimezone(tz=localtimezone)
                )
                localnow = datetime.now(localtimezone)
                localdaynum = (localnow - localday).days
                _LOGGER.debug("Day: %s", localdaynum)
                if "rain" in hour:
                    rain = hour["rain"]
                    if not math.isnan(rain["1h"]):
                        totalrain.update(
                            {localdaynum: totalrain[localdaynum] + rain["1h"]}
                        )
                        _LOGGER.debug("Day: %s Rain: %s", localdaynum, rain)
                        if self._units == "imperial":
                            # convert rainfall to inches
                            attrsrain.update(
                                {
                                    "day_%d_rain"
                                    % (localdaynum): round(
                                        totalrain[localdaynum] / 25.4, 2
                                    )
                                }
                            )
                        else:
                            attrsrain.update(
                                {
                                    "day_%d_rain"
                                    % (localdaynum): round(totalrain[localdaynum], 2)
                                }
                            )

                if "snow" in hour:
                    snow = hour["snow"]
                    if not math.isnan(snow["1h"]):
                        totalsnow.update(
                            {localdaynum: totalsnow[localdaynum] + snow["1h"]}
                        )
                        if self._units == "imperial":
                            # convert snow to inches
                            attrssnow.update(
                                {
                                    "day_%d_snow"
                                    % (localdaynum): round(
                                        totalsnow[localdaynum] / 25.4, 2
                                    )
                                }
                            )
                        else:
                            attrssnow.update(
                                {
                                    "day_%d_snow"
                                    % (localdaynum): round(totalsnow[localdaynum], 2)
                                }
                            )

                if "temp" in hour:
                    if hour["temp"] < mintemp[localdaynum]:
                        mintemp.update({localdaynum: hour["temp"]})
                        attrmin.update({"day_%d_min" % (localdaynum): hour["temp"]})
                    if hour["temp"] > maxtemp[localdaynum]:
                        maxtemp.update({localdaynum: hour["temp"]})
                        attrmax.update({"day_%d_max" % (localdaynum): hour["temp"]})
            # end hour loop
        # end rest loop

        # now loop through the data to calculate the adjustment factor
        equivalent = 0
        for day, daysig in enumerate(self._daysig):
            # calculate rainfall equivalent watering
            # each days rain has varying significance
            # e.g. yesterdays rain is less significant than todays rain
            equivalent += attrsrain["day_%d_rain" % (day)] * daysig

        try:
            if equivalent < self._water_target:
                # calculate the factor
                factor = (self._water_target - equivalent) / self._water_target
                factor = max(0, factor)
            else:
                factor = 0
        except ZeroDivisionError:
            # watering target has been set as 0
            factor = 1

        self.factor = "%.2f" % factor
        # only return 5 entries as the 6th is not a complete 24hrs
        attrsrain.popitem()
        attrssnow.popitem()
        attrmin.popitem()
        attrmax.popitem()
        self.attrs = {**attrsrain, **attrssnow, **attrmin, **attrmax}
