from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from freezegun import freeze_time
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.httpx_client import get_async_client

import custom_components.openweathermaphistory.const as const
from custom_components.openweathermaphistory.weatherhistory import WeatherHistoryV3

TEST_CONFIG = {
    CONF_API_KEY: "XXX",
    const.CONF_LOOKBACK_DAYS: 20,
    const.CONF_MAX_CALLS_PER_HOUR: 100,
    const.CONF_MAX_CALLS_PER_DAY: 200,
    const.CONF_LOOKBACK_DAYS: 20,
}


def test_init_weather_history():
    wh = WeatherHistoryV3(hass=Mock(), config=TEST_CONFIG, units="imperial")
    assert wh.lookback_days == TEST_CONFIG[const.CONF_LOOKBACK_DAYS]
    assert wh._hour_rolling_window.count() == 0
    assert wh.day_request_limit == 200
    assert wh._day_rolling_window.len == timedelta(days=1)


@pytest.mark.asyncio
async def test_api_limits():
    mock_hass = Mock()
    wh = WeatherHistoryV3(hass=mock_hass, config=TEST_CONFIG, units="imperial")
    with pytest.MonkeyPatch.context() as mp:

        # We need to set the request data to make sure our timestamp falls on the hour.
        # We check to make sure the timestamp has minute==0, second==0, microsecond==0
        request_data = MagicMock()
        mp.setattr(
            request_data,
            "json",
            lambda: {"data": [{"dt": 1682254800, "temp": 83.25, "humidity": 67}]},
        )
        mp.setattr(
            "homeassistant.helpers.httpx_client.get_async_client", lambda: Mock()
        )

        get_async_client(mock_hass).request = AsyncMock(return_value=request_data)

        mp.setattr(wh, "async_save", AsyncMock())

        assert wh._hour_rolling_window.count() == 0
        wh.lookback_days
        await wh.backfill_chunk(max_calls=10)
        assert get_async_client(mock_hass).request.call_count == 10
        await wh.backfill_chunk(max_calls=10)
        assert get_async_client(mock_hass).request.call_count == 20

        # hit the limit here, but save 1 for live calls
        await wh.backfill_chunk(max_calls=200)
        assert get_async_client(mock_hass).request.call_count == 99

        # live call should go through
        await wh.async_update()
        assert get_async_client(mock_hass).request.call_count == 100

        # but not again
        await wh.async_update()
        assert get_async_client(mock_hass).request.call_count == 100

        with freeze_time(datetime.now(tz=timezone.utc) + timedelta(hours=1, seconds=1)):
            await wh.backfill_chunk(max_calls=200)
            # day limit, but save enough for live updates the rest of teh day
            assert get_async_client(mock_hass).request.call_count == 200 - 24

            # these still work
            await wh.async_update()
            assert get_async_client(mock_hass).request.call_count == 200 - 24 + 1
