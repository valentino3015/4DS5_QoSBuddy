from stream_window import QoSStream, SlidingWindow
from feature_eng import QoSFeatureEngineer


# =========================
# INIT COMPONENTS
# =========================
stream = QoSStream(
    "data_treatement/qosbuddy_dataset_enhanced.csv",
    delay=2
)

window = SlidingWindow(window_size=10, step=2)

engine = QoSFeatureEngineer()

# =========================
# PIPELINE START
# =========================
print("🚀 QoS STREAMING PIPELINE STARTED\n")

for event in stream.stream():

    # 📡 STREAM → WINDOW
    window.add(event)

    # 🪟 check if window is ready
    if window.is_ready():

        current_window = window.get_window()

        print("\n🪟 WINDOW GENERATED")
        print("=" * 50)

        # (optional) print window
        for row in current_window:
            print(row)

        # 📊 WINDOW → FEATURE ENGINEERING
        features = engine.transform(current_window)

        print("\n🧠 FEATURES GENERATED")
        print("=" * 50)

        for k, v in features.items():
            print(f"{k}: {v}")

      