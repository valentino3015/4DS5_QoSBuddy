import pandas as pd
import time
from datetime import datetime
from collections import deque


# =========================
# 📡 STREAM LAYER
# =========================
class QoSStream:
    def __init__(self, file_path, delay=2):
        self.file_path = file_path
        self.delay = delay
        self.df = pd.read_csv(file_path)
        self.index = 0
        self.total = len(self.df)

    def _format_row(self, row):
        """
        Convert row to dictionary and replace timestamp with real-time
        """
        data = row.to_dict()

        # overwrite timestamp with real-time system timestamp
        data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return data

    def stream(self):
        """
        Generator: yields one event every `delay` seconds
        """
        while self.index < self.total:
            row = self.df.iloc[self.index]
            formatted_row = self._format_row(row)

            yield formatted_row

            self.index += 1
            time.sleep(self.delay)


# =========================
# 🪟 WINDOW LAYER
# =========================
class SlidingWindow:
    def __init__(self, window_size=10, step=2):
        self.window_size = window_size
        self.step = step

        self.buffer = deque(maxlen=window_size)
        self.counter = 0

    def add(self, event):
        """
        Add incoming stream event to buffer
        """
        self.buffer.append(event)
        self.counter += 1

    def is_ready(self):
        """
        Window triggers when:
        - buffer is full
        - step condition is met
        """
        return len(self.buffer) == self.window_size and self.counter % self.step == 0

    def get_window(self):
        """
        Return raw window (list of rows)
        """
        return list(self.buffer)


# =========================
# 🔥 PIPELINE EXECUTION
# =========================
if __name__ == "__main__":

    # 📡 init stream
    stream = QoSStream(
        "data_treatement/qosbuddy_dataset_enhanced.csv",
        delay=2
    )

    # 🪟 init window
    window = SlidingWindow(window_size=10, step=2)

    print("🚀 Starting QoS streaming pipeline...\n")

    # 🔁 main loop
    for event in stream.stream():

        # 1. push stream event into window
        window.add(event)

        # 2. when window is ready → process it
        if window.is_ready():

            current_window = window.get_window()

            print("\n🪟 WINDOW GENERATED")
            print("=" * 40)

            for row in current_window:
                print(row)

            