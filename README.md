# openweathremaphistory
A home assistant sensor that uses the OpenWeatherMap API to return the last 5 days rainfall, min and max temperatures as attributes. The data is in 24 hout time slots not date based but data for the preceeding 24hrs.

The scan_interval is set at 30 minutes as OpenWeatherMap data only refreshes every hour.

This information is used to calculate a factor that can be used to reduce the watering time of the [Irrigation Program](https://github.com/petergridge/irrigation_component_V4) custom component.

A OpenWeatherMap API Key is required see the [OpenWeatherMap](https://www.home-assistant.io/integrations/openweathermap/) custom component for more information.

You need an API key, which is free, but requires a [registration](https://home.openweathermap.org/users/sign_up).

## Attributes

Attributes are returned for:
* daily rainfall - day_0_rainfall ... day_4_rainfall
* daily minimum temperature - day_0_min ... day_4_min
* daily maximum temperature - day_0_max ... day_4_max

## Installation

* Copy the openweathermaphistory folder to the ‘config/custom components/’ directory 

A minimal configuration. Latitude and Longitude are defaulted to your Home Assistant location
```yaml
sensor:
  - platform: openweathermaphistory
    name: 'rainfactor'
    api_key: 'open weather map api key'
```

A fully specified configuration.
```yaml
sensor:
  - platform: openweathermaphistory
    name: 'rainfactor'
    latitude: -33.8302547
    longitude: 151.1516128
    api_key: 'open weather map api key'
    num_days: 5
    day0min: 1
    day0max: 5
    day1min: 6
    day1max: 10  
    day2min: 11
    day2max: 15  
    day3min: 16
    day3max: 20  
    day4min: 21
    day4max: 25  
    fine_icon: 'mdi:weather-sunny'
    lightrain_icon: 'mdi:weather-rainy'
    rain_icon: 'mdi:weather-pouring'
```

|Key |Type|Optional|Description|Default|
|---|---|---|---|---|
|platform|string|Required|the sensor entityopenweathermaphistory|
|name|string|Required|display name for the sensor|'rainfactor'|
|api_key|string|Required|the OpenWeatherMap API key|
|unit_system|string|Optional|metric or imperial|metric|
|latitude|latitude|Optional|the location to obtain weather information for|home assistant configured Latitude and Longitude|
|longitude|longitude|Optional|the location to obtain weather information for|home assistant configured Latitude and Longitude|
|num_days|integer|Optional|the number of days to collect data for|4, 0 will return the lat 24 hours data only|
|fine_icon|icon|Optional|the icon to use when the factor = 1|'mdi:weather-sunny'|
|lightrain_icon|icon|Optional|the icon to use when the factor somewhere between 0 and 1|'mdi:weather-rainy'|
|rain_icon|icon|Optional|the icon to use when the factor = 0|'mdi:weather-pouring'|
|day0min|integer|Optional|the lower limit for the calculation of Day 0 (today's) factor|1|
|day0max|integer|Optional|the upper limit for the calculation of Day 0 (today's) factor|5|
|day1min|integer|Optional|the lower limit for the calculation of Day 1 (yesterday's) factor|6|
|day1max|integer|Optional|the upper limit for the calculation of Day 1 (yesterday's) factor|10|
|day2min|integer|Optional|the lower limit for the calculation of Day 2 factor|11|
|day2max|integer|Optional|the upper limit for the calculation of Day 2 factor|15|
|day3min|integer|Optional|the lower limit for the calculation of Day 3 factor|16|
|day3max|integer|Optional|the upper limit for the calculation of Day 3 factor|20|
|day4min|integer|Optional|the lower limit for the calculation of Day 4 factor|21|
|day4max|integer|Optional|the upper limit for the calculation of Day 4 factor|25|

## State Calculation

The adjustment factor is calculated based on the the cumulative rainfall for each day. For yesterday the cumulative value is today's (day 0) rainfall + yesterday's (day 1) rainfall.

The lowest factor of the up to five days of rainfall is return as the state of the sensor.

factor = 1 - ((cumulative rainfall - daymin)/(daymax - daymin))

If the factor is less than 0 the factor is set to 0.

## REVISION HISTORY

### 1.0.0
* Initial Release.

### 1.0.1
* fix refresh issues, reduce API calls

### 1.0.2
* fix remaining bug

### 1.0.3
* Refactored the logic into a class
* Fixed issue with daily refresh - changed to UTC time
* Expanded attributes to include min and max temperature
* Unit system (metric, imperial) config option

### 1.0.4
* Reduce refresh time to 30 minutes
* Remove cumulative rain from the attributes

### 1.0.5
* Add unique id
* round factor to 2 decimal places

### 1.0.6
* refactor to present data based on the last 24 hours
* Added custom card
