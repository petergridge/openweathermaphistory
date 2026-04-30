"""Test the OpenWeatherMap History weather entity."""

from __future__ import annotations

import logging
from pathlib import Path
import sys
from unittest.mock import patch

from homeassistant.components.weather import (
    ATTR_CONDITION_EXCEPTIONAL,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
    ATTR_FORECAST_CLOUD_COVERAGE,
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_HUMIDITY,
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_PRESSURE,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator


# Create a mock HomeAssistant for tests that need it
class MockHomeAssistant:
    def __init__(self):
        self.data = {}


ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = ROOT / "config"
if str(CONFIG_PATH) not in sys.path:
    sys.path.insert(0, str(CONFIG_PATH))

from custom_components.openweathermaphistory.const import DOMAIN
from custom_components.openweathermaphistory.weather import (
    OpenWeatherHistoryWeather,
    _map_condition,
    async_setup_entry,
)


class DummyWeather:
    def __init__(self) -> None:
        self._data = {
            "current": {
                "temp": 18.5,
                "pressure": 1013,
                "humidity": 65,
                "wind_speed": 4.3,
                "wind_deg": 135,
                "clouds": 60,
                "rain": 0.5,
                "snow": 0.0,
                "description": "Light rain",
            },
            "f0": {
                "datetime": "2026-04-27T12:00:00+00:00",
                "max_temp": 20.0,
                "min_temp": 14.0,
                "rain": 0.8,
                "snow": 0.0,
                "pressure": 1015,
                "humidity": 70,
                "wind_speed": 5.5,
                "wind_deg": 180,
                "clouds": 75,
                "description": "Light rain",
            },
            "f1": {
                "datetime": "2026-04-28T12:00:00+00:00",
                "max_temp": 22.0,
                "min_temp": 15.0,
                "rain": 0.0,
                "snow": 0.2,
                "pressure": 1012,
                "humidity": 55,
                "wind_speed": 3.1,
                "wind_deg": 90,
                "clouds": 20,
                "description": "Snow",
            },
        }

    def processed_value(self, period, value):
        return self._data.get(period, {}).get(value, 0)

    def daily_count(self):
        return 2

    def remaining_backlog(self):
        return 4


class _DummyIntegrationFrame:
    def __init__(self) -> None:
        self.custom_integration = True
        self.filename = "custom_components/openweathermaphistory/weather.py"
        self.integration = "openweathermaphistory"
        self.module = "custom_components.openweathermaphistory.weather"
        self.relative_filename = self.filename
        self.line_number = 1
        self.line = ""


class DummyCoordinator:
    def __init__(self, hass: HomeAssistant, weather: DummyWeather) -> None:
        self.hass = hass
        self.data = weather
        self.name = "test"
        self.update_interval = None

    async def _async_update_data(self):
        return self.data


def test_map_condition() -> None:
    assert _map_condition("light rain") == ATTR_CONDITION_RAINY
    assert _map_condition("clear sky") == ATTR_CONDITION_SUNNY
    assert _map_condition("snow showers") == ATTR_CONDITION_SNOWY
    assert _map_condition("strong wind") == ATTR_CONDITION_WINDY
    assert _map_condition("mysterious weather") == ATTR_CONDITION_EXCEPTIONAL
    assert _map_condition(None) is None


async def test_weather_entity_properties() -> None:
    hass = MockHomeAssistant()
    coordinator = DummyCoordinator(hass, DummyWeather())
    entity = OpenWeatherHistoryWeather("test-id", coordinator)

    assert entity.native_temperature == 18.5
    assert entity.native_pressure == 1013
    assert entity.humidity == 65
    assert entity.native_wind_speed == 4.3
    assert entity.wind_bearing == 135
    assert entity.cloud_coverage == 60
    assert entity.native_precipitation == 0.5
    assert entity.condition == ATTR_CONDITION_RAINY
    assert entity.extra_state_attributes == {
        "daily_count": 2,
        "remaining_backlog": 4,
        "current_description": "Light rain",
    }


async def test_forecast_daily() -> None:
    hass = MockHomeAssistant()
    coordinator = DummyCoordinator(hass, DummyWeather())
    entity = OpenWeatherHistoryWeather("test-id", coordinator)

    forecast = entity._async_forecast_daily()

    assert forecast is not None
    assert len(forecast) == 2
    assert forecast[0][ATTR_FORECAST_TIME] == "2026-04-27T12:00:00+00:00"
    assert forecast[0][ATTR_FORECAST_NATIVE_TEMP] == 20.0
    assert forecast[0][ATTR_FORECAST_NATIVE_TEMP_LOW] == 14.0
    assert forecast[0][ATTR_FORECAST_NATIVE_PRECIPITATION] == 0.8
    assert forecast[0][ATTR_FORECAST_CONDITION] == ATTR_CONDITION_RAINY
    assert forecast[0][ATTR_FORECAST_NATIVE_PRESSURE] == 1015
    assert forecast[0][ATTR_FORECAST_NATIVE_WIND_SPEED] == 5.5
    assert forecast[0][ATTR_FORECAST_WIND_BEARING] == 180
    assert forecast[0][ATTR_FORECAST_HUMIDITY] == 70
    assert forecast[0][ATTR_FORECAST_CLOUD_COVERAGE] == 75


async def test_async_setup_entry() -> None:
    """Test async_setup_entry for weather platform."""
    from unittest.mock import AsyncMock, MagicMock

    hass = MockHomeAssistant()

    # Create a mock config entry
    config_entry = MagicMock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry_id"

    # Create mock coordinator
    coordinator = DummyCoordinator(hass, DummyWeather())

    # Set up hass.data structure
    hass.data[DOMAIN] = {config_entry.entry_id: {"coordinator": coordinator}}

    # Mock async_add_entities
    async_add_entities = AsyncMock()

    # Call async_setup_entry
    await async_setup_entry(hass, config_entry, async_add_entities)

    # Verify that async_add_entities was called with the weather entity
    assert async_add_entities.call_count == 1
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], OpenWeatherHistoryWeather)
    assert entities[0]._attr_unique_id == config_entry.entry_id
