"""Process-local admission limit for the documented single-backend deployment."""

from collections import deque
from threading import Lock
from time import monotonic


class ExecutionRateLimiter:
    def __init__(self, maximum: int, *, clock=monotonic):
        self.maximum, self.clock = maximum, clock
        self.starts = deque()
        self.lock = Lock()

    def admit(self) -> bool:
        with self.lock:
            now = self.clock()
            while self.starts and self.starts[0] <= now - 60:
                self.starts.popleft()
            if len(self.starts) >= self.maximum:
                return False
            self.starts.append(now)
            return True
