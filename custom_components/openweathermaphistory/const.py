'''weather history class defn constants'''

CONST_API_CALL          = 'https://api.openweathermap.org/data/3.0/onecall/timemachine?lat=%s&lon=%s&dt=%s&appid=%s&units=metric'
CONST_API_FORECAST      = 'https://api.openweathermap.org/data/3.0/onecall?lat=%s&lon=%s&exclude=minutely,alerts&appid=%s&units=metric'
ATTR_API_VER            = 'api_ver'
CONF_RESOURCES          = "resources"
CONF_FORMULA            = "formula"
CONF_DATA               = "data"
CONF_ATTRIBUTES         = "attributes"
CONF_MAX_DAYS           = "max_days"
CONF_INTIAL_DAYS        = "initial_days"
CONF_PRECISION          = "numeric_precision"
CONF_STATECLASS         = "state_class"
CONF_SENSORCLASS        = "sensor_class"

