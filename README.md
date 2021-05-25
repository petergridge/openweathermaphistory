# openweathremaphistory
A home assistant sensor that uses the OpenWeatherMap API to get the last 5 days rainfall. A call is made for each day so the scan_interval is set at 3600 seconds (1 hour) as the free tier allows only 1000 calls per day.

This information is used to calculate a factor that can be used to reduce the watering time of the [Irrigation Program](https://github.com/petergridge/irrigation_component_V3) custom component.

A OpenWeatherMap API Key is required see the [OpenWeatherMap](https://www.home-assistant.io/integrations/openweathermap/) custom component for more information.

You need an API key, which is free, but requires a [registration](https://home.openweathermap.org/users/sign_up).

## Calculation

The adjustment factor is calculated based on the the cumulative rainfall for each day. For yesterday the cumulative value is today's (day 0) rainfall + yesterday's (day 1) rainfall.

The lowest factor of the up to five days of rainfall is return as the state of the sensor.

factor = 1 - ((cumulative rainfall - daymin)/(daymax - daymin))

If the factor is less than 0 the factor is set to 0.

## Attributes

Attributes are returned for:
* daily rainfall
* daily cumulative rainfall

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
    day5min: 26
    day5max: 30
    fine_icon: 'mdi:weather-sunny'
    lightrain_icon: 'mdi:weather-rainy'
    rain_icon: 'mdi:weather-pouring'
```

## platform
*(string)(Required)* the sensor entityopenweathermaphistory.
>#### name
*(string)(Required)* display name for the sensor, defaults to 'rainfactor'
>#### api_key
*(string)(Required)* the OpenWeatherMap API key.
>#### latitude
*(latitude)(Optional)* the location to obtain weather information for, defaults to the home assistant configured Latitude and Longitude
>#### longitude
*(longitude)(Optional)* the location to obtain weather information for, defaults to the home assistant configured Latitude and Longitude
>#### num_days
*(integer)(Optional)* the number of days to collect data for, deafaults to 5, 0 will return today's data only
>#### fine_icon
*(icon)(Optional)* the icon to use when the factor = 1, defaults to 'mdi:weather-sunny'
>#### lightrain_icon
*(icon)(Optional)* the icon to use when the factor somewhere between 0 and 1, defaults to 'mdi:weather-rainy'
>#### rain_icon
*(icon)(Optional)* the icon to use when the factor = 0, defaults to 'mdi:weather-pouring'
>#### day0min
*(integer)(Optional)* the lower limit for the calculation of Day 0 (today's) factor, default 1
>#### day0max
*(integer)(Optional)* the upper limit for the calculation of Day 0 (today's) factor, default 5
>#### day1min
*(integer)(Optional)* the lower limit for the calculation of Day 1 (yesterday's) factor, default 6
>#### day1max
*(integer)(Optional)* the upper limit for the calculation of Day 1 (yesterday's) factor, default 10
>#### day2min
*(integer)(Optional)* the lower limit for the calculation of Day 2 factor, default 11
>#### day2max
*(integer)(Optional)* the upper limit for the calculation of Day 2 factor, default 15
>#### day3min
*(integer)(Optional)* the lower limit for the calculation of Day 3 factor, default 16
>#### day3max
*(integer)(Optional)* the upper limit for the calculation of Day 3 factor, default 20
>#### day4min
*(integer)(Optional)* the lower limit for the calculation of Day 4 factor, default 21
>#### day4max
*(integer)(Optional)* the upper limit for the calculation of Day 4 factor, default 25
>#### day5min
*(integer)(Optional)* the lower limit for the calculation of Day 5 factor, default 26
>#### day5max
*(integer)(Optional)* the upper limit for the calculation of Day 5 factor, default 30

## REVISION HISTORY

### 1.0.0
* Initial Release.

### 1.0.0
* fix refresh issues, reduce API calls
