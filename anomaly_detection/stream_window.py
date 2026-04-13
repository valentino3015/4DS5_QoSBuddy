import pandas as pd
import time
from datetime import datetime
from collections import deque


class QoSStream:
    def __init__(self, file_path, delay=0.0):
        self.file_path = file_path
        self.delay = delay
        self.df = pd.read_csv(file_path)
        self.index = 0
        self.total = len(self.df)

    def _format_row(self, row):
        data = row.to_dict()
        data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return data

    def stream(self):
        while self.index < self.total:
            row = self.df.iloc[self.index]
            yield self._format_row(row)
            self.index += 1
            if self.delay > 0:
                time.sleep(self.delay)


class SlidingWindow:
    def __init__(self, window_size=10, step=2):
        self.window_size = window_size
        self.step = step
        self.buffer = deque(maxlen=window_size)
        self.counter = 0

    def add(self, event):
        self.buffer.append(event)
        self.counter += 1

    def is_ready(self):
        return len(self.buffer) == self.window_size and self.counter % self.step == 0

    def get_window(self):
        return list(self.buffer)