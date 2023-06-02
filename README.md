# OpenWeatherMapHistory
[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?logo=homeassistantcommunitystore)](https://github.com/hacs/integration)
[![my_badge](https://img.shields.io/badge/Home%20Assistant-Community-41BDF5.svg?logo=homeassistant)](https://community.home-assistant.io/t/custom-component-to-retrieve-five-days-of-rain-history-from-openweathermap/310153)
![GitHub release (latest by date)](https://img.shields.io/github/downloads/petergridge/openweathermaphistory/latest/total)
[![Validate with hassfest](https://github.com/petergridge/openweathermaphistory/actions/workflows/hassfest.yml/badge.svg)](https://github.com/petergridge/openweathermaphistory/actions/workflows/hassfest.yml)
[![HACS Action](https://github.com/petergridge/openweathermaphistory/actions/workflows/hacs.yml/badge.svg)](https://github.com/petergridge/openweathermaphistory/actions/workflows/hacs.yml)

# NEW to Version 2.0.0
- A totally new way to access the data!
- Supports Jinja templates to provide you control over how you utilise the data.
- Current Observations
- 8 days of forecast
- Up to 30 days of history

This is a big update, if you find an issue raise an issue on Github, If you like it give it a star.

# Thanks
A big thanks to @tsbernar for the work put into this release.

# Breaking Change: V2.0.0
- Existing yaml will no longer work, you will need to set up using the config flow.

# Functionality
A home assistant sensor that uses the OpenWeatherMap API to return:
- Up to 30 days of history data (rain, snow, min temp, max temp)
- 7 days of forecast (pop, rain, snow, humidity, min temp, max temp)
- Current observations (rain, snow, humidity, current temp, current pressure)
- Status information (remaining backlog to load, current days API count)

Any number sensors can be created using templates.

While HA recommends using individual sensors, you can assign additional attributes to a sensor.

The data is in 24 hour time slots, not date based, but data for the preceeding 24hrs.

Two API calls are used each hour, one to collect the new history data and another to collect the forecast and current observations.

When a new locations is created: 
- Two API calls are made to collect the current observations and the last hour.
- Every refresh cycle (defaults to 10 min) 24 calls (1 day) will be made to load the history data (default 5 days) until the API limit (default 500) has been reached or all data has been provisioned.

You can configure the retention of the data so while you may choose to backload 5 days you can keep up to 30 days of data. This will be accumulated until the limit is reached.

This integration was initially built to support the [Irrigation Program](https://github.com/petergridge/irrigation_component_V4) custom component and can be used to:
- alter the watering time/volume
- alter the watering frequency

You need an API key, which is free, but requires a [registration](https://openweathermap.org/api). You do need to provide a payment method, however, the first 1000 calls are free and you can set an upper limit of calls. Setting this to 1000 will prevent you incurring any costs.

## Installation

HACS installation
Adding as a custom repository using HACS is the simplest approach, will be published soon.

Manual Installation
* Copy the openweathermaphistory folder to the ‘config/custom components/’ directory 

## Configuration Config Flow
- Define the program using the UI. From Setting, Devices & Services choose 'ADD INTEGRATION'. Search for OpenWeatherMap History.
- Add the integration multiple times if you want more than one location. The second location must be at least 1000m away from any previously configured location to prevent accidental creation of 'duplicate' weather monitoring. Be aware that the API limit is for each location. Locations are not aware of API usage by any other location configured.

## Location
|Key |Type|Optional|Description|Default|
|---|---|---|---|---|
|Location Name|string|Required|Instance identifier, cannot be modified|Home Assistant configured name|
|API Key|string|Required|OpenWeatherMap API key||
|Location|location|Required|Select from the map, cannot be within 1000m of an already configured location|Home Assistant configure location|
|Days to keep data|integer|Required|Retention period of the captured data. Can be longer than initial download. Data will accumulate as collected until the limit is reached. Will default to backload days it is defined with a value less thant the backload days|5 days|
|Days to backload|integer|Required|Days for initial population, can be increased after the initial load, a new backload will commence|5 days|
|Max API calls per day|integer|Required|The daily API limit, the count is accumulated across all instances of the integration|500|

<img width="427" alt="image" src="https://github.com/petergridge/Irrigation-V5/assets/40281772/3aa18655-52e3-4b84-b9a8-7ceb75f320bd">

## Sensor
Key |Type|Optional|Description|Default|
|---|---|---|---|---|
|Sensor name|string|Required|Sensor name, modify using HA once created||
|Jinja2 Template|template|Required|A valid template that will define the sensor||
|Attributes to expose|string|Optional|A comma seperated list of valid variables to add as attributes to the sensor||
|Sensor Type|string|Optional|Select the type to define unit of measure. A template that returns a text value must be set to None|None|

<img width="287" alt="image" src="https://github.com/petergridge/Irrigation-V5/assets/40281772/ef095fee-67c5-4895-9e10-a81c33385206"><img width="286" alt="image" src="https://github.com/petergridge/Irrigation-V5/assets/40281772/ac77c8ed-d6e4-4621-a1b9-7bab956259c9">

## Units of measure
All data is captured in metric measurements.

To ensure that you see the information in your local unit of measure:
- Ensure you select the appropriate 'Type of sensor'. This will allow HA to display information in the unit of measure defined for your instance.
- If you change the type of sensor you will see warnings in the log as the unit of measure will be inconsistent, go to the developers tools/statistics page to fix the issue.
```
WARNING (Recorder) [homeassistant.components.sensor.recorder] The unit of sensor.current_temp (°C) cannot be converted ...
Go to https://my.home-assistant.io/redirect/developer_statistics to fix this
```
- You can change the unit of measure (°C to °F) for each sensor in the sensor settings.

## Resources
Two files are created in the config directory:
- One named for the instance of the integration with a '.pickle' extension
- The other is 'owm_api_count.pickle' that retains the daily API cound across all instances of the integration

## Attribute example
```
day0rain, day1rain, day2rain, day3rain, day4rain, day0max, day1max, day2max, day3max, day4max, day0min, day1min, day2min, day3min, day4min
```
## Jinja2 Template 
Calculations are performed in the native unit of measure, so all calculations are in mm, mm/hr, °C, hPa, %.

### Examples
Determine the watering frequency based on temperature
```
{% set avgtemp = (forecast1max + forecast2max + forecast3max)/3 %}
{% if avgtemp < 10 %}
Off
{% elif avgtemp < 20 %}
Mon, Fri
{% else %}
Mon, Thu, Sat
{% endif %}
```
Display current temperature
```
{{current_temp}}
```
Version 1 factor, verifying to an expected 10mm rainfall
```
{{ 
  [(10 
  - day0rain 
  - day1rain*0.5
  - day2rain*0.25
  - day3rain*0.12
  - day4rain*0.06)/10
  ,0]|max
}}
```
## Using the cumulative data (under development)
A common usecase is to show daily/monthly rainfall. Using the cumulative data elements this can be achieved with the [Utility Meter sensor](https://www.home-assistant.io/integrations/utility_meter/)

## Available variables
### For each day of history available, day 0 represent the past 24 hours
|Variable|example|Description|
|---|---|---|
|day{i}rain|day0rain|Rainfall in the 24 hour period|
|day{i}snow|day1snow|Snow in the 25-48 hour period|
|day{i}max||Maximum temperature in the 24 hour period|
|day{i}min||Minimum temperature in the 24 hour period|
### Forecast provides 7 days of data, day 0 represent the future 24 hours
|Variable|example|Description|
|---|---|---|
|forecast{i}pop|forecast0pop|Probobility of precipitation in the 24 hour period|
|forecast{i}rain|forecast1rain|Forecast rain in the 25-48 hour period|
|forecast{i}snow||Forecast snow in the 24 hour period|
|forecast{i}humidity||Average humidity|
|forecast{i}max||Maximum temperature in the 24 hour period|
|forecast{i}min||Minimum temperature in the 24 hour period|
### Current observations
|Variable|Description|
|---|---|
|current_rain|Current hours rainfall|
|current_snow|Current hours snow|
|current_humidity|Current hours humidity|
|current_temp|Current hours temperature|
|current_pressure|Current hours pressure|
### Cumulative totals (under development)
|cumulative_rain|Continually increasing total of all rainfall recorded|
|cumulative_snow|Continually increasing total of all snowfall recorded|
### Status values
|Variable|Description|
|---|---|
|remaining_backlog|Hours of data remaining to be gathered|
|daily_count|Number of API calls for all instances of the integration, resets midnight GMT. This will not always match between instance of the integration due to the update frequency|

## REVISION HISTORY
### 2.0.4 under development
- Add cummulative rain and snow to support meter sensor
- fix issue with sensor class 'none'
### 2.0.0
- Add current observation and forecast information
- Support the collection of more than 5 days of data
- Monitor API usage
- Move to config flow for configuration
- Each attribute can be exposed as a sensor
- Sensors are defined by Jinja templates
### 1.1.2
- Version 1.2 supports Open Weather Map API 3 functionally this version remains the same as version 1.1
- A new registration is required for version 3, but once configured the API Key remains the same.
- **Upgrade only after registering for API version 3**
- Implement Pickle to store data to limit api calls when when restarting
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
