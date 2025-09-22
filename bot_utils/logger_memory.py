from collections import deque
import logging


class LastLogsHandler(logging.Handler):
    """A logging handler that keeps the last N log records in memory."""

    def __init__(self, capacity=30):
        super().__init__()
        self.records = deque(maxlen=capacity)
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s.%(msecs)03d %(module)s %(levelname)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record):
        self.records.append(self.format(record))

    def get_last_logs(self):
        return list(self.records)
