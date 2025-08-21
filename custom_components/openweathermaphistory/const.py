"""Weather history class defn constants."""

DOMAIN = "openweathermaphistory"
CONST_API_AGGREGATE = "https://api.openweathermap.org/data/3.0/onecall/day_summary?lat=%s&lon=%s&date=%s&appid=%s&units=metric"
CONST_API_CALL      = "https://api.openweathermap.org/data/3.0/onecall/timemachine?lat=%s&lon=%s&dt=%s&appid=%s&units=metric"
CONST_API_FORECAST  = "https://api.openweathermap.org/data/3.0/onecall?lat=%s&lon=%s&exclude=minutely,alerts&appid=%s&units=metric"
CONST_API_OVERVIEW  = "https://api.openweathermap.org/data/3.0/onecall/overview?lat=%s&lon=%s&appid=%s"
CONF_CREATE_SENSORS = "create_sensors"
CONF_FORMULA = "formula"
CONF_DATA = "data"
CONF_ATTRIBUTES = "attributes"
CONF_MAX_DAYS = "max_days"
CONF_INTIAL_DAYS = "initial_days"
CONF_PRECISION = "numeric_precision"
CONF_STATECLASS = "state_class"
CONF_SENSORCLASS = "sensor_class"
CONF_UID = "unique_id"

# prevent accidental duplicate instances
CONST_PROXIMITY = 1000
# max calls in a single refresh
CONST_CALLS = 24
CONST_INITIAL = "initial"
# max calls in any 24 hour period
CONF_MAX_CALLS = "max_calls"

ATTRIBUTION = "Data provided by OpenWeatherMap"

OPTIONS_SOURCE = ["FORECAST", "HOURLY", "AGGREGATE"]
OPTIONS_SENSOR_CLASS = [
    "none",
    "humidity",
    "precipitation",
    "precipitation_intensity",
    "temperature",
    "pressure",
]
OPTIONS_BULK = [
    "current_obs",
    "hist_rain",
    "hist_snow",
    "hist_max",
    "hist_min",
    "forecast_rain",
    "forecast_snow",
    "forecast_max",
    "forecast_min",
    "forecast_humidity",
    "forecast_pop",
]
