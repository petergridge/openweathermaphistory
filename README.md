# OpenWeatherMapHistory
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?logo=homeassistantcommunitystore)](https://github.com/hacs/integration)
![GitHub release (latest by date)](https://img.shields.io/github/downloads/petergridge/openweathermaphistory/latest/total)
[![Validate with hassfest](https://github.com/petergridge/openweathermaphistory/actions/workflows/hassfest.yml/badge.svg)](https://github.com/petergridge/openweathermaphistory/actions/workflows/hassfest.yml)
[![HACS Action](https://github.com/petergridge/openweathermaphistory/actions/workflows/hacs.yml/badge.svg)](https://github.com/petergridge/openweathermaphistory/actions/workflows/hacs.yml)

# Breaking Change: V1.0.11 to V1.1.0.
The following configuration options have been removed, see updated factor calculation below
|Key |Type|Optional|Description|
|---|---|---|---|
|num_days|integer|Optional|the number of days to collect data for|
|day0min|integer|Optional|the lower limit for the calculation of Day 0 (today's) factor|
|day0max|integer|Optional|the upper limit for the calculation of Day 0 (today's) factor|
|day1min|integer|Optional|the lower limit for the calculation of Day 1 (yesterday's) factor|
|day1max|integer|Optional|the upper limit for the calculation of Day 1 (yesterday's) factor|
|day2min|integer|Optional|the lower limit for the calculation of Day 2 factor|
|day2max|integer|Optional|the upper limit for the calculation of Day 2 factor|
|day3min|integer|Optional|the lower limit for the calculation of Day 3 factor|
|day3max|integer|Optional|the upper limit for the calculation of Day 3 factor|
|day4min|integer|Optional|the lower limit for the calculation of Day 4 factor|
|day4max|integer|Optional|the upper limit for the calculation of Day 4 factor|

# Functionality
A home assistant sensor that uses the OpenWeatherMap API to return the last 5 days rainfall, snow, min and max temperatures as attributes. The data is in 24 hour time slots, not date based, but data for the preceeding 24hrs.

The scan_interval is set at 30 minutes as OpenWeatherMap data only refreshes every hour. A 24 hour period will make 54 API calls.

This information is used to calculate a factor that can be used to reduce the watering time of the [Irrigation Program](https://github.com/petergridge/irrigation_component_V4) custom component.

A OpenWeatherMap API Key is required see the [OpenWeatherMap](https://www.home-assistant.io/integrations/openweathermap/) custom component for more information.

You need an API key, which is free, but requires a [registration](https://home.openweathermap.org/users/sign_up).

## Attributes

Attributes are returned for:
* daily rainfall - day_0_rainfall ... day_4_rainfall
* daily snow - day_0_snow ... day_4_snow
* daily minimum temperature - day_0_min ... day_4_min
* daily maximum temperature - day_0_max ... day_4_max

## Installation

HACS installation
Adding as a custom repository using HACS is the simplest approach, will be published soon.

Manual Installation
* Copy the openweathermaphistory folder to the ‘config/custom components/’ directory 

## Configuration
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
    day0sig: 1
    day1sig: 0.5
    day2sig: 0.25
    day3sig: 0.12
    day4sig: 0.06
    watertarget: 10
    fine_icon: 'mdi:weather-sunny'
    lightrain_icon: 'mdi:weather-rainy'
    rain_icon: 'mdi:weather-pouring'
```

|Key |Type|Optional|Description|Default|
|---|---|---|---|---|
|platform|string|Required|the sensor entityopenweathermaphistory|
|name|string|Required|display name for the sensor|'rainfactor'|
|api_key|string|Required|the OpenWeatherMap API key|
|latitude|latitude|Optional|the location to obtain weather information for|home assistant configured Latitude and Longitude|
|longitude|longitude|Optional|the location to obtain weather information for|home assistant configured Latitude and Longitude|
|num_days|integer|Optional|the number of days to collect data for|4, 0 will return the lat 24 hours data only|
|fine_icon|icon|Optional|the icon to use when the factor = 1|'mdi:weather-sunny'|
|lightrain_icon|icon|Optional|the icon to use when the factor somewhere between 0 and 1|'mdi:weather-rainy'|
|rain_icon|icon|Optional|the icon to use when the factor = 0|'mdi:weather-pouring'|
|day0sig|float|Optional|Significance of the days rainfall|1|
|day1sig|float|Optional|Significance of the days rainfall|0.5|
|day2sig|float|Optional|Significance of the days rainfall|0.25|
|day3sig|float|Optional|Significance of the days rainfall|0.12|
|day4sig|float|Optional|Significance of the days rainfall|0.06|
|watertarget|float|Optional|The desired watering to be applied|10|

## State Calculation

The adjustment factor is calculated based on the the cumulative rainfall for each day.

Each 24 hrs rain has a lower significance as it ages:
- Rain in the last 24 hours has a weighting of 1
- rain for the next 24 hours has a weighting of 0.5
- rain for the next 24 hours has a weighting of 0.25
- rain for the next 24 hours has a weighting of 0.12
- rain for the next 24 hours has a weighting of 0.06

The adjusted total rainfall is compared to a target rainfall:
- if the total adjusted rainfall is 2mm and the target rainfall is 10mm a factor of 0.8 will be returned

## REVISION HISTORY
### 1.1.1
- For HACS
### 1.1.0
- Breaking Change - remove num_days configuration option.
- Breaking Change - Modify the factor to a simpler model
- Optimised API calls
- Handle missing time zone issue for new OpenWeather registrations. Timezone defaults to HomeAssistant configuration value
- Only return five full 24hr periods

### 1.0.11
* Deprecate unit_system and derive units from HA config.
### 1.0.10
* Minor bug fix
### 1.0.9
* present rainfall in inches when imperial unit system selected
### 1.0.6
* refactor to present data based on the last 24 hours
* Added custom card
### 1.0.5
* Add unique id
* round factor to 2 decimal places
### 1.0.4
* Reduce refresh time to 30 minutes
* Remove cumulative rain from the attributes
### 1.0.3
* Refactored the logic into a class
* Fixed issue with daily refresh - changed to UTC time
* Expanded attributes to include min and max temperature
* Unit system (metric, imperial) config option
### 1.0.2
* fix remaining bug
### 1.0.1
* fix refresh issues, reduce API calls
### 1.0.0
* Initial Release.
