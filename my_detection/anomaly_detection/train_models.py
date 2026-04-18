import numpy as np
import pandas as pd
import joblib
import os

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from lstm_autoencoder import LSTMAutoencoder
from feature_eng import QoSFeatureEngineer

# =========================
# CONFIG
# =========================
DATA_PATH = "data_treatement/qosbuddy_dataset_enhanced.csv"
WINDOW_SIZE = 10
MODEL_DIR = "models"

os.makedirs(MODEL_DIR, exist_ok=True)

fe = QoSFeatureEngineer()

# =========================
# LOAD DATA
# =========================
df = pd.read_csv(DATA_PATH)
df = df.sort_values("timestamp").reset_index(drop=True)

# =========================
# WINDOWS
# =========================
windows = [
    df.iloc[i:i+WINDOW_SIZE].to_dict(orient="records")
    for i in range(len(df) - WINDOW_SIZE)
]

# =========================
# ENGINEERED FEATURES (ONLY ONCE SOURCE OF TRUTH)
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

X = []
y = []

for w in windows:
    f = fe.transform(w)
    X.append([f[k] for k in FEATURES])
    y.append(w[-1]["any_degradation"])

X = np.array(X)
y = np.array(y)

print("Training ML feature shape:", X.shape)

# =========================
# SCALER
# =========================
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

joblib.dump(scaler, f"{MODEL_DIR}/scaler.pkl")

# =========================
# ISOLATION FOREST
# =========================
iso = IsolationForest(contamination=0.1, random_state=42)
iso.fit(X_scaled)
joblib.dump(iso, f"{MODEL_DIR}/isolation.pkl")

# =========================
# XGBOOST
# =========================
xgb = XGBClassifier(
    n_estimators=100,
    max_depth=5,
    eval_metric="logloss"
)
xgb.fit(X_scaled, y)
joblib.dump(xgb, f"{MODEL_DIR}/xgb.pkl")

# =========================
# LSTM INPUT
# =========================
lstm_seq = []

for w in windows:
    seq = []
    for r in w:
        seq.append([
            r["rsrp"], r["sinr"], r["rsrq"],
            r["throughput_dl"], r["latency_ms"],
            r["prb_util_dl_pct"], r["bler_dl_pct"],
            r["mos"]
        ])
    lstm_seq.append(seq)

lstm_seq = np.array(lstm_seq)

lstm = LSTMAutoencoder(input_shape=(WINDOW_SIZE, 8))

train_errors = lstm.train(lstm_seq)

lstm.save("models/lstm.keras")

np.save("models/lstm_train_errors.npy", train_errors)

print("✅ TRAINING COMPLETE")