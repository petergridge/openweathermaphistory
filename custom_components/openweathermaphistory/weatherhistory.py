"""Support for RESTful API."""
import logging
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from functools import cached_property
from json import JSONEncoder

from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_LOOKBACK_DAYS,
    CONF_MAX_CALLS_PER_DAY,
    CONF_MAX_CALLS_PER_HOUR,
    CONST_API_CALL,
    STORAGE_DAY_KEY,
    STORAGE_HISTORY_KEY,
    STORAGE_HOUR_KEY,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .data import RestData
from .util import RollingWindow

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


class WeatherHistory:
    """Class for handling the weather data retrieval for the v3.0 api."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigType,
        units: str,
        url_template: str = CONST_API_CALL,
    ):
        self.lookback_days = config[CONF_LOOKBACK_DAYS]
        self._hourly_history: deque[tuple[datetime, WeatherData]] = deque(
            maxlen=self.lookback_days * 24
        )

        self.lat = config.get(CONF_LATITUDE, hass.config.latitude)
        self.lon = config.get(CONF_LONGITUDE, hass.config.longitude)

        # Store data unique to location
        key = STORAGE_KEY + "." + self.location
        self._store = Store[
            dict[str, deque[tuple[datetime, WeatherData] | deque[datetime]]]
        ](hass, STORAGE_VERSION, key, encoder=WeatherEncoder)

        self.hass = hass
        self.units = units
        self._url_template = url_template
        self._key = config[CONF_API_KEY]

        self.hour_request_limit: int = config[CONF_MAX_CALLS_PER_HOUR]
        self.day_request_limit: int = config[CONF_MAX_CALLS_PER_DAY]
        self._hour_rolling_window = RollingWindow(len=timedelta(hours=1))
        self._day_rolling_window = RollingWindow(len=timedelta(days=1))

    def _make_url(self, date: datetime) -> str:
        fmt_date = int(date.timestamp())
        return self._url_template % (
            self.lat,
            self.lon,
            fmt_date,
            self._key,
            self.units,
        )

    @cached_property
    def location(self) -> str:
        return f"{self.lat}_{self.lon}"

    async def async_load(self):
        """Load data from persistent storage"""
        if (data := await self._store.async_load()) is None:
            _LOGGER.debug("No data from storage: %s", self._store.path)
            return

        _LOGGER.debug("Loaded data from storage: %s", self._store.path)

        if STORAGE_HISTORY_KEY in data and data[STORAGE_HISTORY_KEY]:
            self._hourly_history.clear()
            for dt_str, wd_dict in data[STORAGE_HISTORY_KEY]:
                dt = datetime.fromisoformat(dt_str)
                wd = WeatherData(**wd_dict)
                self._hourly_history.append((dt, wd))

        if STORAGE_HOUR_KEY in data and data[STORAGE_HOUR_KEY]:
            for dt_str in data[STORAGE_HOUR_KEY]:
                dt = datetime.fromisoformat(dt_str)
                self._hour_rolling_window.data.append(dt)

        if STORAGE_DAY_KEY in data and data[STORAGE_DAY_KEY]:
            for dt_str in data[STORAGE_DAY_KEY]:
                dt = datetime.fromisoformat(dt_str)
                self._day_rolling_window.data.append(dt)

    async def async_save(self):
        data = {
            STORAGE_HISTORY_KEY: self._hourly_history,
            STORAGE_DAY_KEY: self._day_rolling_window.data,
            STORAGE_HOUR_KEY: self._hour_rolling_window.data,
        }
        _LOGGER.debug(
            "Saving data. %s \n hourly_history (len: %s)\n day_rolling_window "
            + "(len: %s)\n hour_rolling_window (len: %s)",
            self._store.path,
            len(self._hourly_history),
            len(self._day_rolling_window.data),
            len(self._hour_rolling_window.data),
        )
        await self._store.async_save(data)

    async def backfill_chunk(self, max_calls: int = 10):
        """Backfill hourly data for self.lookback_days days.
        Continue backfilling for up to `max_calls` api requests.
        NOTE: This requires 1 api call per hour on v3 api."""

        end_dt = datetime.now(tz=timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )
        start_dt = end_dt - timedelta(days=self.lookback_days)

        if len(self._hourly_history) == self.lookback_days * 24:
            # No need to backfill if we have all data
            return

        _LOGGER.info(
            "Continuing backfill of weather data for %s between %s and %s (%s)",
            self.location,
            start_dt,
            end_dt,
            start_dt <= end_dt,
        )

        dt_to_data = {d[0]: d[1] for d in self._hourly_history}

        self._hourly_history.clear()
        remaining_calls = max_calls

        while end_dt >= start_dt:
            if end_dt in dt_to_data:
                # If we already have the data, no need to request
                self._hourly_history.appendleft((end_dt, dt_to_data[end_dt]))
            else:
                if remaining_calls > 0:
                    await self._async_update_for_datetime(end_dt)
                    remaining_calls -= 1

            end_dt -= timedelta(hours=1)

        await self.async_save()

    async def async_update(self) -> bool:
        """Get update for top of the current hour"""
        date = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
        result = await self._async_update_for_datetime(date, live=True)
        await self.async_save()
        return result

    def _check_limits(self, live: bool = False) -> bool:
        hour_limit = self.hour_request_limit
        day_limit = self.day_request_limit
        if not live:
            hour_limit -= 1
            day_limit -= 24  # reserve enough to request once per hour live

        if self._hour_rolling_window.count() >= hour_limit:
            _LOGGER.info(
                "Hourly request limit hit for %s (%s of %s).",
                self.location,
                self._hour_rolling_window.count(),
                self.hour_request_limit,
            )
            return False

        if self._day_rolling_window.count() >= day_limit:
            _LOGGER.info(
                "Day request limit hit for %s (%s of %s).",
                self.location,
                self._day_rolling_window.count(),
                self.day_request_limit,
            )
            return False

        _LOGGER.debug(
            "No limits hit, used limits for %s: day: (%s / %s), hour: (%s / %s)",
            self.location,
            self._day_rolling_window.count(),
            self.day_request_limit,
            self._hour_rolling_window.count(),
            self.hour_request_limit,
        )

        return True

    async def _async_get_rest_data(self, url: str, live: bool = False) -> RestData:
        data = RestData()
        if not self._check_limits(live=live):
            return data

        await data.set_resource(self.hass, url)
        await data.async_update(log_errors=False)

        self._hour_rolling_window.increment()
        self._day_rolling_window.increment()

        return data

    async def _async_update_for_datetime(
        self, date: datetime, live: bool = False
    ) -> bool:
        _LOGGER.debug("Updating weather history for %s at %s", self.location, date)

        if self._hourly_history and self._hourly_history[0][0] == date:
            _LOGGER.debug("Already have observation for %s, skipping", date)
            return False

        url = self._make_url(date)
        data = await self._async_get_rest_data(url, live=live)

        if data.data is None:
            _LOGGER.debug("Got no data for %s !", date)
            return False
        return self.add_observation(data)

    def _get_1hr_precipitation(self, data: dict, field: str) -> float:
        total = 0
        if field in data and isinstance(data[field], dict):
            for k, v in data[field].items():
                if k == "1h":
                    total += v
                elif k == "3h":
                    """
                    Sometimes the API will return "3h" instead of "1h".  This is not documented on the v3
                    API docs (https://openweathermap.org/api/one-call-3#hist_example), but it is in the v2.5
                    (https://openweathermap.org/history) docs.

                    From observation, it seems like the 3 hour total is always repeated for 3 consecutive hourly
                    observations.  If we divide the number by 3, we will get 1/3 of the 3 hour total in each 1 hour
                    observation, recording the correct total over the period.

                    Discussed here: https://github.com/petergridge/openweathermaphistory/pull/14#issuecomment-1519084629
                    """
                    total += v / 3.0

                else:
                    _LOGGER.critical("Unknown key in %s data: %s \n%s", field, k, data)

        return total

    def add_observation(self, data: RestData) -> bool:
        json_data: dict = data.data["data"][0]

        dt = datetime.fromtimestamp(json_data["dt"], tz=timezone.utc)

        # We only expect observations on the hour, our calculations will not work
        # as expected if we have more frequent observations.
        if (dt.minute != 0) or (dt.second != 0) or (dt.microsecond != 0):
            _LOGGER.critical(
                "Unexpected timestamp in observation, does not fall on the hour. Skipping. ts: %s\n"
                + "%s\nurl: %s",
                dt,
                json_data,
                data._resource,
            )
            return False

        rain = self._get_1hr_precipitation(json_data, "rain")
        snow = self._get_1hr_precipitation(json_data, "snow")

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
                    "Missing observation.  Current dt: %s last dt: %s.",
                    dt,
                    last_dt,
                )

            elif last_dt == dt:
                _LOGGER.warning(
                    "Already seen observation for: %s, skipping.",
                    dt,
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
        return self.total_attr(start, end, attr)

    def total_attr(self, start: datetime, end: datetime, attr: str) -> float:
        total = 0.0
        high = -999.0
        low = 999.0
        count = 0

        for dt, wd in self._hourly_history:
            if (dt >= start) and (dt < end):
                match attr:
                    case "snow":
                        total += wd.snow
                    case "rain":
                        total += wd.rain
                    case "humidity":
                        total += wd.humidity
                        count += 1
                    case "temp_high":
                        if wd.temp > high:
                            high = wd.temp
                    case "temp_low":
                        if wd.temp < low:
                            low = wd.temp
                    case _:
                        raise ValueError("Unknown attr: %s", attr)

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
