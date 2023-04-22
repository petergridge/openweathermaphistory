from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from custom_components.openweathermaphistory.util import RollingWindow


@pytest.mark.parametrize(
    "window_size",
    [timedelta(hours=2), timedelta(days=3, hours=3), timedelta(seconds=5)],
)
def test_rolling_window(window_size: timedelta):
    rolling_window = RollingWindow(len=window_size)

    assert rolling_window.len == window_size
    assert rolling_window.count() == 0

    for i in range(100):
        rolling_window.increment()

    assert rolling_window.count() == 100

    with freeze_time(datetime.now() + window_size + timedelta(seconds=1)):
        assert rolling_window.count() == 0
