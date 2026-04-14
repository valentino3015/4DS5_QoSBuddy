import numpy as np
import pandas as pd
import joblib
import tensorflow as tf

from stream_window import QoSStream, SlidingWindow
from feature_eng import QoSFeatureEngineer
from explain_engine import QoSExplainEngine

MODEL_DIR = "models"

scaler = joblib.load(f"{MODEL_DIR}/scaler.pkl")
iso = joblib.load(f"{MODEL_DIR}/isolation.pkl")
xgb = joblib.load(f"{MODEL_DIR}/xgb.pkl")
lstm = tf.keras.models.load_model(f"{MODEL_DIR}/lstm.keras")

fe = QoSFeatureEngineer()
explainer = QoSExplainEngine("anomaly_detection/kpi_mapping.json")

WINDOW_SIZE = 10

FEATURES = [
    "mean_sinr",
    "mean_rsrp",
    "mean_rsrq",
    "mean_throughput_dl",
    "mean_latency",
    "mean_prb_dl",
    "mean_prb_ul",
    "mean_mos"
]

stream = QoSStream("data_treatement/qosbuddy_dataset_enhanced.csv", delay=2)
window = SlidingWindow(WINDOW_SIZE, step=2)

print("🚀 REAL-TIME PIPELINE STARTED")

for event in stream.stream():
    window.add(event)

    if not window.is_ready():
        continue

    w = window.get_window()

    # =========================
    # FEATURES
    # =========================
    f = fe.transform(w)
    x = np.array([f[k] for k in FEATURES]).reshape(1, -1)
    x = scaler.transform(x)

    # =========================
    # ISO FOREST (%)
    # =========================
    iso_raw = -iso.decision_function(x)[0]
    iso_score = 1 - np.exp(-iso_raw)

    # =========================
    # XGBOOST (%)
    # =========================
    xgb_score = xgb.predict_proba(x)[0][1]

    # =========================
    # LSTM (%)
    # =========================
    seq = np.array([[
        r["rsrp"], r["sinr"], r["rsrq"],
        r["throughput_dl"], r["latency_ms"],
        r["prb_util_dl_pct"], r["bler_dl_pct"],
        r["mos"]
    ] for r in w]).reshape(1, WINDOW_SIZE, 8)

    recon = lstm.predict(seq, verbose=0)
    mse = np.mean((seq - recon) ** 2)

    lstm_score = 1 - np.exp(-mse / 50)

    # =========================
    # FINAL SCORE (%)
    # =========================
    final_score = (
        0.3 * iso_score +
        0.4 * xgb_score +
        0.3 * lstm_score
    ) * 100

    # =========================
    # SEVERITY
    # =========================
    if final_score < 30:
        severity = "OK"
    elif final_score < 70:
        severity = "WARNING"
    else:
        severity = "CRITICAL"

    # =========================
    # ROOT CAUSE
    # =========================
    causes = explainer.get_root_cause(w)

    # =========================
    # PRINT CLEAN OUTPUT
    # =========================
    print("\n🪟 WINDOW RESULT")
    print(f"IF Score: {iso_score*100:.1f}%")
    print(f"XGB Score: {xgb_score*100:.1f}%")
    print(f"LSTM Score: {lstm_score*100:.1f}%")
    print(f"\nFINAL SCORE: {final_score:.1f}%")
    print(f"SEVERITY: {severity}")

    print("ROOT CAUSE:")
    for c in causes:
        print(" -", c)

    print("=" * 50)