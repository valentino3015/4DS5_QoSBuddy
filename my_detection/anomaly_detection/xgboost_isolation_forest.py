import numpy as np
import pandas as pd
import joblib
import tensorflow as tf

from lstm_autoencoder import LSTMAutoencoder
from feature_eng import QoSFeatureEngineer

# =========================
# FEATURES (ONLY ML MODELS)
# =========================
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


class RuleBasedDetector:
    def check(self, f):
        v = 0
        if f["mean_sinr"] < 0: v += 1
        if f["mean_rsrp"] < -100: v += 1
        if f["mean_latency"] > 100: v += 1
        if f["mean_prb_dl"] > 85: v += 1
        return v


class MultiModelScorer:

    def __init__(self, model_dir="models"):
        self.fe = QoSFeatureEngineer()

        self.scaler = joblib.load(f"{model_dir}/scaler.pkl")
        self.iso = joblib.load(f"{model_dir}/isolation.pkl")
        self.xgb = joblib.load(f"{model_dir}/xgb.pkl")
        self.lstm = tf.keras.models.load_model(f"{model_dir}/lstm.keras")

        self.rules = RuleBasedDetector()

        self.window_size = 10

    def _vector(self, f):
        x = np.array([f[k] for k in FEATURES]).reshape(1, -1)
        return self.scaler.transform(x)

    def score(self, window):

        f = self.fe.transform(window)
        x = self._vector(f)

        iso_score = -self.iso.decision_function(x)[0]
        xgb_score = self.xgb.predict_proba(x)[0][1]

        seq = np.array([[
            r["rsrp"], r["sinr"], r["rsrq"],
            r["throughput_dl"], r["latency_ms"],
            r["prb_util_dl_pct"], r["bler_dl_pct"],
            r["mos"]
        ] for r in window])

        seq = seq.reshape(1, self.window_size, 8)

        recon = self.lstm.predict(seq, verbose=0)
        lstm_score = np.mean((seq - recon) ** 2)

        rule_score = self.rules.check(f) / 4

        final = (
            0.3 * iso_score +
            0.4 * xgb_score +
            0.2 * lstm_score +
            0.1 * rule_score
        )

        return {
            "if_score": float(iso_score),
            "xgb_score": float(xgb_score),
            "lstm_score": float(lstm_score),
            "rule_score": float(rule_score),
            "final_score": float(final)
        }