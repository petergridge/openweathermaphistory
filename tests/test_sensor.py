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
from custom_components.openweathermaphistory.weatherhistory import WeatherHistory

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

REST_DATA = [
    """ {"data": [{"dt": 1682265600, "temp": 83.25, "humidity": 67, "rain": {"1h": 0.32}}]} """,
    """ {"data": [{"dt": 1682262000, "temp": 83.25, "humidity": 67, "rain": {"1h": 0.32}}]}""",
    """ {"data": [{"dt": 1682258400, "temp": 83.25, "humidity": 67, "rain": {"1h": 0.32}}]}""",
    """ {"data": [{"dt": 1682254800, "temp": 83.25, "humidity": 67, "rain": {"1h": 0.32}}]}""",
    """ {"data": [{"dt": 1682251200, "temp": 83.25, "humidity": 67, "rain": {"1h": 0.32}}]}""",
]

REST_DATA_WITH_3H = [
    """ {"data": [{"dt": 1682265600, "temp": 83.25, "humidity": 67, "rain": {"1h": 1}}]} """,
    """ {"data": [{"dt": 1682262000, "temp": 83.25, "humidity": 67, "rain": {"1h": 1}}]}""",
    """ {"data": [{"dt": 1682258400, "temp": 83.25, "humidity": 67, "rain": {"1h": 1}}]}""",
    """ {"data": [{"dt": 1682254800, "temp": 83.25, "humidity": 67, "rain": {"3h": 1}}]}""",
    """ {"data": [{"dt": 1682251200, "temp": 83.25, "humidity": 67, "rain": {"3h": 1}}]}""",
    """ {"data": [{"dt": 1682247600, "temp": 83.25, "humidity": 67, "rain": {"3h": 1}}]}""",
]


@pytest.fixture
def weather_history():
    mock_hass = Mock()
    wh = WeatherHistory(hass=mock_hass, config=TEST_CONFIG, units="metric")

    for rd in REST_DATA:
        data = RestData()
        data.data = json.loads(rd)
        wh.add_observation(data)

    assert len(wh._hourly_history) == 5
    return wh


@pytest.fixture
def weather_history_with_3h():
    mock_hass = Mock()
    wh = WeatherHistory(hass=mock_hass, config=TEST_CONFIG, units="metric")

    for rd in REST_DATA_WITH_3H:
        data = RestData()
        data.data = json.loads(rd)
        wh.add_observation(data)

    return wh


@pytest.fixture
def sensor_registry(weather_history: WeatherHistory):
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


def test_3h_handling(
    sensor_registry: RainSensorRegistry, weather_history_with_3h: WeatherHistory
):
    sensor_registry._weather_history = weather_history_with_3h
    assert "total_rain_sensor" in sensor_registry._registry

    sensor: RainSensor = sensor_registry._registry["total_rain_sensor"]
    now = datetime.fromtimestamp(1682275600, tz=timezone.utc)

    with freeze_time(now):
        total = sensor_registry._evaluate_total_rain(sensor)
        # Expect a total of 3 from the 1h samples, plus 1/3 * 3 for the 3h samples
        assert pytest.approx(total) == 4
