# openweathremaphistory
A home assistant sensor that uses the OpenWeatherMap API to get the last 5 days rainfall.

This information is used to calculate a factor that can be used to reduce the watering time of the Irrigation Program custom component.

A OpenWeatherMap API Key is required see the OpenWeatherMap custom component for more information:

https://www.home-assistant.io/integrations/openweathermap/

## Calculation

The adjustment factor is calculated based on the the cummulative rain fall for each day. For yesterday the cummulative value is today's rainall + yesterday's rainfall.

The lowest factor of the up to five days of rainfall is return as the state of the sensor.

factor = 1 - ((cummulative rainfall - daymin)/(daymax - daymin))
if the factor is less than 0 the factor is set to 0.

## Attributes

Attributes are also returned for:
* daily rainfall
* daily cummulative rainfall


## Installation

### To create a working sample
* Copy the openweathermaphistory folder to the ‘config/custom components/’ directory 


```yaml
  - platform: openweathermaphistory
    name: 'rainfactor'
    latitude: 0
    longitude: 0
    api_key: 'open weather map api key'
    num_days: 1
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

## program
*(string)(Required)* the sensor entity.
>#### name
*(string)(Optional)* display name for the sensor, defaults to 'rainfactor'
>#### latitude
*(string)(Required)* the OpenWeatherMap API key.
>#### latitude
*(latitude)(Optional)* the location to obtain weather information for, defaults to the home assistant configured Latitude and Longitude
>#### longitude
*(longitude)(Optional)* the location to obtain weather information for, defaults to the home assistant configured Latitude and Longitude
>#### longitude
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
>#### day4min
*(integer)(Optional)* the lower limit for the calculation of Day 5 factor, default 26
>#### day4max
*(integer)(Optional)* the upper limit for the calculation of Day 5 factor, default 30




