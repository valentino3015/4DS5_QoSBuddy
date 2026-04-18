import pandas as pd
import time
from datetime import datetime
from collections import deque


class QoSStream:
    def __init__(self, file_path, delay=2):
        self.file_path = file_path
        self.delay = delay

        # =========================
        # 🔥 SAFE CSV LOADING (NO Sniffer)
        # =========================
        try:
            self.df = pd.read_csv(file_path, sep=",", engine="python")
            if self.df.shape[1] == 1:
                raise ValueError("comma failed")
        except:
            self.df = pd.read_csv(file_path, sep=";", engine="python")

        # =========================
        # 🧹 CLEAN COLUMNS
        # =========================
        self.df.columns = (
            self.df.columns
            .str.strip()
            .str.replace(" ", "_")
            .str.replace("__", "_")
        )

        self.df = self.df.loc[:, ~self.df.columns.duplicated()]

        print("✅ Final columns:", list(self.df.columns))

        # =========================
        # 🚨 HARD CHECK (CRITICAL)
        # =========================
        required = ["sinr", "rsrp", "rsrq"]
        missing = [c for c in required if c not in self.df.columns]

        if missing:
            raise ValueError(f"❌ Missing required columns: {missing}")

        self.index = 0
        self.total = len(self.df)

    def _format_row(self, row):
        data = row.to_dict()
        data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return data

    def stream(self):
        while self.index < self.total:
            yield self._format_row(self.df.iloc[self.index])
            self.index += 1
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