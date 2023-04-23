import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from freezegun import freeze_time
from homeassistant.const import CONF_API_KEY

import custom_components.openweathermaphistory.const as const
from custom_components.openweathermaphistory.data import RestData
from custom_components.openweathermaphistory.sensor import (
    RainSensor,
    RainSensorRegistry,
)
from custom_components.openweathermaphistory.weatherhistory import WeatherHistoryV3

TEST_CONFIG = {
    CONF_API_KEY: "XXX",
    const.CONF_LOOKBACK_DAYS: 20,
    const.CONF_MAX_CALLS_PER_HOUR: 100,
    const.CONF_MAX_CALLS_PER_DAY: 200,
    const.CONF_LOOKBACK_DAYS: 20,
    const.CONF_RESOURCES: [
        {
            const.CONF_TYPE: "total_rain",
            const.CONF_NAME: "total_rain_sensor",
            const.CONF_DATA: {
                const.CONF_START_HOUR: -24,
                const.CONF_END_HOUR: 0,
            },
        }
    ],
    const.ATTR_ICON_FINE: "x",
    const.ATTR_ICON_LIGHTRAIN: "x",
    const.ATTR_ICON_RAIN: "x",
}


@pytest.fixture
def weather_history():
    mock_hass = Mock()
    wh = WeatherHistoryV3(hass=mock_hass, config=TEST_CONFIG, units="metric")

    rest_data = [
        """ {"data": [{"dt": 1682265600, "temp": 83.25, "humidity": 67, "rain": {"1h": 0.32}}]} """,
        """ {"data": [{"dt": 1682264600, "temp": 83.25, "humidity": 67, "rain": {"1h": 0.32}}]}""",
        """ {"data": [{"dt": 1682263600, "temp": 83.25, "humidity": 67, "rain": {"1h": 0.32}}]}""",
        """ {"data": [{"dt": 1682262600, "temp": 83.25, "humidity": 67, "rain": {"1h": 0.32}}]}""",
        """ {"data": [{"dt": 1682261600, "temp": 83.25, "humidity": 67, "rain": {"1h": 0.32}}]}""",
    ]
    for rd in rest_data:
        data = RestData()
        data.data = json.loads(rd)
        wh.add_observation(data)

    assert len(wh._hourly_history) == 5
    return wh


@pytest.fixture
def sensor_registry(weather_history: WeatherHistoryV3):
    mock_hass = Mock()
    sr = RainSensorRegistry(mock_hass, TEST_CONFIG, "metric")
    sr._weather_history = weather_history
    return sr


def test_total_rain_calc(sensor_registry: RainSensorRegistry):
    assert "total_rain_sensor" in sensor_registry._registry
    sensor: RainSensor = sensor_registry._registry["total_rain_sensor"]
    now = datetime.fromtimestamp(1682275600, tz=timezone.utc)
    with freeze_time(now):
        total = sensor_registry._evaluate_total_rain(sensor)
        assert pytest.approx(total) == 1.6
