from collections import deque
from datetime import datetime, timedelta, timezone


class RollingWindow:
    """Class to handle rolling window counter for rate-limiting"""

    def __init__(self, len: timedelta):
        self._len: timedelta = len
        self.data: deque[datetime] = deque()

    def increment(self) -> int:
        """Increments the counter and returns the count."""
        ts = datetime.now(tz=timezone.utc)
        self.data.appendleft(ts)
        return self.count()

    def _clean_up(self):
        if len(self.data) == 0:
            return

        cutoff = datetime.now(tz=timezone.utc) - self._len

        while len(self.data) and (self.data[-1] < cutoff):
            self.data.pop()

    def count(self) -> int:
        """Returns the count, but does not increment the counter."""
        self._clean_up()
        return len(self.data)

    @property
    def len(self):
        return self._len
