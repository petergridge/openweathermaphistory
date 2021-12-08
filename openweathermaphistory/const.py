DOMAIN                  = 'openweathermaphistory'
SENSOR_ID_FORMAT        = 'sensor' + '.{}'
CONST_ENTITY            = 'entity_id'
CONST_SENSOR            = 'sensor'
CONST_API_CALL          = 'https://api.openweathermap.org/data/2.5/onecall/timemachine?lat=%s&lon=%s&dt=%s&appid=%s&units=%s'


ATTR_DAYS               = 'num_days' #limit the number of days/API calls
ATTR_0_MAX              = 'day0max'  #Day 0 - today max rainfall test threshold
ATTR_0_MIN              = 'day0min'  #Day 0 - today, min ranfall test threshold
ATTR_1_MAX              = 'day1max'  #Day 1 - yesterday, max rain threshold
ATTR_1_MIN              = 'day1min'
ATTR_2_MAX              = 'day2max'  #Day 2 - two days ago
ATTR_2_MIN              = 'day2min'
ATTR_3_MAX              = 'day3max'
ATTR_3_MIN              = 'day3min'
ATTR_4_MAX              = 'day4max'
ATTR_4_MIN              = 'day4min'
ATTR_5_MAX              = 'day5max'
ATTR_5_MIN              = 'day5min'
ATTR_ICON_FINE          = 'fine_icon'       #icon to display when factor is 1
ATTR_ICON_LIGHTRAIN     = 'lightrain_icon'  #icon to display when factor is > 0 and <1
ATTR_ICON_RAIN          = 'rain_icon'       #icon to display when factor is 0


DFLT_ICON_FINE          = 'mdi:weather-sunny'
DFLT_ICON_LIGHTRAIN     = 'mdi:weather-rainy'
DFLT_ICON_RAIN          = 'mdi:weather-pouring'