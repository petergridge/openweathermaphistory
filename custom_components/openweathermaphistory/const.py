"""weather history class defn constants"""

CONST_API_CALL = "https://api.openweathermap.org/data/3.0/onecall/timemachine?lat=%s&lon=%s&dt=%s&appid=%s&units=%s"

CONF_DATA = "data"
CONF_FORMULA = "formula"
CONF_RESOURCES = "resources"
CONF_TYPE = "type"
CONF_V3_API = "v3_api"
CONF_NAME = "name"
CONF_START_HOUR = "start_hour"
CONF_END_HOUR = "end_hour"
CONF_LOOKBACK_DAYS = "lookback_days"
CONF_MAX_CALLS_PER_HOUR = "max_api_calls_per_hour"
CONF_MAX_CALLS_PER_DAY = "max_api_calls_per_day"

TYPE_CUSTOM = "custom"
TYPE_DEFAULT_FACTOR = "default_factor"
TYPE_TOTAL_RAIN = "total_rain"
SENSOR_TYPES = [TYPE_CUSTOM, TYPE_DEFAULT_FACTOR, TYPE_TOTAL_RAIN]

STORAGE_VERSION = 1
STORAGE_KEY = "openweathermaphistory.history"
STORAGE_HISTORY_KEY = "hourly_history"
STORAGE_HOUR_KEY = "hour_rolling_window"
STORAGE_DAY_KEY = "day_rolling_window"

ATTR_ICON_FINE = "fine_icon"  # icon to display when factor is 1
# icon to display when factor is > 0 and <1
ATTR_ICON_LIGHTRAIN = "lightrain_icon"
ATTR_ICON_RAIN = "rain_icon"  # icon to display when factor is 0
DFLT_ICON_FINE = "mdi:weather-sunny"
DFLT_ICON_LIGHTRAIN = "mdi:weather-rainy"
DFLT_ICON_RAIN = "mdi:weather-pouring"

ATTR_0_SIG = "day0sig"
ATTR_1_SIG = "day1sig"
ATTR_2_SIG = "day2sig"
ATTR_3_SIG = "day3sig"
ATTR_4_SIG = "day4sig"
ATTR_WATERTARGET = "watertarget"
