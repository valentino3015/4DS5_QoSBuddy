"""
QoSBuddy -- DetectionAgent
======================================================
Unified anomaly detection and root-cause analysis agent.

Pipeline:
  1. BATCH TRAINING   — trains GRU-AE, Temporal-CNN, GRU-Predictor,
                        and SARIMA per-cell forecasters (anomaly detection)
                        plus XGBoost + RF classifiers + k-NN index (root cause
                        analysis) on historical CSV data.
  2. LIVE INFERENCE   — streams time_series_kpi.csv row-by-row,
                        runs rule engine + DL ensemble (GRU) + SARIMA + neighbour
                        correlation, and for every anomaly, performs
                        inline RCA (XGBoost + SHAP + k-NN).
                        Emits structured JSON events to rca_feed.jsonl.

Output feed: data/output/rca_feed.jsonl

Usage:
    python agents/detection_agent.py --mode all           # train + stream (default)
    python agents/detection_agent.py --mode train         # batch train only
    python agents/detection_agent.py --mode stream        # inference only (loads saved models)
    python agents/detection_agent.py --sample-frac 0.15
    python agents/detection_agent.py --seq-len 16
    python agents/detection_agent.py --stream-delay 0.0
    python agents/detection_agent.py --cell gNB_001_C1
    python agents/detection_agent.py --chunk-size 500
    mlflow ui --backend-store-uri sqlite:///mlflow_tracking.db
"""

import os, sys, json, time, logging, argparse, warnings, math
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict, deque, OrderedDict
from copy import deepcopy
from tqdm import tqdm

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report
from sklearn.neighbors import NearestNeighbors
import joblib
import xgboost as xgb

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
from statsmodels.tsa.arima.model import ARIMA

import mlflow
import mlflow.pytorch
import mlflow.sklearn
import shap

warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
warnings.filterwarnings("ignore", category=UserWarning, module="mlflow")
os.environ["PYTHONWARNINGS"] = "ignore"
# Suppress Triton warning (not available on Windows, does not affect functionality)
logging.getLogger("torch.utils.flop_counter").setLevel(logging.ERROR)
# Suppress MLflow sklearn serialization warning
logging.getLogger("mlflow.sklearn").setLevel(logging.ERROR)
logging.getLogger("mlflow.models.model").setLevel(logging.ERROR)


# ═══════════════════════════════════════════════════════════════════════════════
# EARLY STOPPING UTILITY
# ═══════════════════════════════════════════════════════════════════════════════
class EarlyStopping:
    """Monitors validation loss and triggers early stop when no improvement."""
    def __init__(self, patience: int = 4, min_delta: float = 1e-4):
        self.patience  = patience
        self.min_delta = min_delta
        self.best_loss = float("inf")
        self.counter   = 0
        self.stopped   = False

    def step(self, loss: float) -> bool:
        if loss < self.best_loss - self.min_delta:
            self.best_loss = loss
            self.counter   = 0
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.stopped = True
        return self.stopped

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
DATA_DIR    = ROOT / "data"
MODEL_DIR   = ROOT / "models"
OUTPUT_DIR  = DATA_DIR / "output"
LOG_DIR     = ROOT / "logs"
DASHBOARD_DIR = ROOT / "dashboard"

for d in [MODEL_DIR, OUTPUT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Input data
TS_KPI_PATH    = DATA_DIR / "time_series_kpi.csv"
INCIDENTS_PATH = DATA_DIR / "labeled_incidents.csv"

# Output feed
RCA_FEED = OUTPUT_DIR / "rca_feed.jsonl"

# Anomaly detection models
SCALER_PATH = MODEL_DIR / "scaler.joblib"
SARIMA_PATH = MODEL_DIR / "sarima_forecasters.joblib"

# RCA models
XGB_PATH         = MODEL_DIR / "rca_xgb_classifier.joblib"
RCA_SCALER_PATH  = MODEL_DIR / "rca_scaler.joblib"
LABEL_ENC_PATH   = MODEL_DIR / "rca_label_encoder.joblib"
KNN_PATH         = MODEL_DIR / "rca_knn_index.joblib"
INCIDENT_DB_PATH = MODEL_DIR / "rca_incident_db.joblib"

# ─── Logging ──────────────────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_stream_handler = logging.StreamHandler(sys.stdout)
_file_handler   = logging.FileHandler(LOG_DIR / "detection_agent.log", encoding="utf-8")
_formatter      = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
_stream_handler.setFormatter(_formatter)
_file_handler.setFormatter(_formatter)

logging.basicConfig(level=logging.INFO, handlers=[_stream_handler, _file_handler])
log = logging.getLogger("DetectionAgent")

# ─── KPI feature columns ──────────────────────────────────────────────────────
# Full set used by anomaly detection (Agent 1 side)
KPI_FEATURES_ANOMALY = [
    "RSRP_dBm", "SINR_dB", "PRB_util_DL_pct", "PRB_util_UL_pct",
    "CQI", "BLER_DL_pct", "BLER_UL_pct",
    "throughput_DL_Mbps", "throughput_UL_Mbps", "latency_ms",
    "call_drop_rate_pct", "HO_success_rate_pct", "MOS", "MIMO_rank",
    "active_users",
]

# Features available in labeled_incidents.csv (RCA side)
KPI_FEATURES_INCIDENTS = [
    "RSRP_dBm", "SINR_dB", "PRB_util_DL_pct",
    "CQI", "BLER_DL_pct",
    "throughput_DL_Mbps", "latency_ms",
    "call_drop_rate_pct", "HO_success_rate_pct", "MOS", "MIMO_rank",
]

# Runtime RCA feature list — may be overwritten during training
KPI_FEATURES_RCA = KPI_FEATURES_INCIDENTS

# ─── Rule-based thresholds (domain knowledge) ─────────────────────────────────
THRESHOLDS = {
    "RSRP_dBm":            {"min": -110, "label": "Poor coverage"},
    "SINR_dB":             {"min": 0,    "label": "High interference"},
    "PRB_util_DL_pct":     {"max": 85,   "label": "DL capacity saturation"},
    "PRB_util_UL_pct":     {"max": 80,   "label": "UL capacity saturation"},
    "CQI":                 {"min": 4,    "label": "Poor channel quality"},
    "BLER_DL_pct":         {"max": 10,   "label": "Excessive DL block errors"},
    "BLER_UL_pct":         {"max": 10,   "label": "Excessive UL block errors"},
    "latency_ms":          {"max": 80,   "label": "High latency"},
    "call_drop_rate_pct":  {"max": 3,    "label": "Excessive call drops"},
    "HO_success_rate_pct": {"min": 80,   "label": "Handover degradation"},
    "MOS":                 {"min": 2.5,  "label": "Poor voice quality"},
    "throughput_DL_Mbps":  {"min": 10,   "label": "Very low DL throughput"},
}

SEVERITY_MAP = {
    0: "normal",
    1: "low",
    2: "medium",
    3: "high",
    4: "critical",
}

# ─── RCA: cause → solution mapping ────────────────────────────────────────────
RCA_MAPPING_PATH = DATA_DIR / "rca_mapping.json"
try:
    with open(RCA_MAPPING_PATH, "r", encoding="utf-8") as _f:
        _mapping = json.load(_f)
        CAUSE_TO_SOLUTION = _mapping.get("CAUSE_TO_SOLUTION", {})
        CAUSE_TO_TAG = _mapping.get("CAUSE_TO_TAG", {})
except (FileNotFoundError, json.JSONDecodeError):
    log.warning(f"Failed to load {RCA_MAPPING_PATH}, using empty mappings.")
    CAUSE_TO_SOLUTION = {}
    CAUSE_TO_TAG = {}


# ══════════════════════════════════════════════════════════════════════════════
# DEEP LEARNING ANOMALY MODELS
# ══════════════════════════════════════════════════════════════════════════════
class GRUAutoencoder(nn.Module):
    """
    Trained on NORMAL sequences only.
    High reconstruction error at inference -> likely anomaly.
    Uses GRU for faster streaming performance than LSTM.
    """
    def __init__(self, input_dim: int, hidden_dim: int = 64, latent_dim: int = 16, num_layers: int = 2):
        super().__init__()
        self.encoder_gru = nn.GRU(input_dim, hidden_dim, num_layers, batch_first=True, dropout=0.2 if num_layers > 1 else 0)
        self.encoder_fc   = nn.Linear(hidden_dim, latent_dim)
        self.decoder_fc   = nn.Linear(latent_dim, hidden_dim)
        self.decoder_gru = nn.GRU(hidden_dim, hidden_dim, num_layers, batch_first=True, dropout=0.2 if num_layers > 1 else 0)
        self.decoder_out  = nn.Linear(hidden_dim, input_dim)
        self.register_buffer('mse_p5',  torch.tensor(0.0))
        self.register_buffer('mse_p95', torch.tensor(1.0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, h = self.encoder_gru(x)
        latent    = self.encoder_fc(h[-1])
        repeated  = self.decoder_fc(latent).unsqueeze(1).repeat(1, x.shape[1], 1)
        out, _    = self.decoder_gru(repeated)
        return self.decoder_out(out)

    def anomaly_score(self, x: torch.Tensor) -> np.ndarray:
        self.eval()
        with torch.no_grad():
            mse   = torch.mean((x - self.forward(x)) ** 2, dim=(1, 2))
            score = (mse - self.mse_p5) / (self.mse_p95 - self.mse_p5 + 1e-8)
            return score.clamp(0, 1).cpu().numpy()

    def calibrate(self, normal_tensor: torch.Tensor):
        self.eval()
        with torch.no_grad():
            mse = torch.mean((normal_tensor - self.forward(normal_tensor)) ** 2, dim=(1, 2))
            self.mse_p5  = torch.quantile(mse, 0.05)
            self.mse_p95 = torch.quantile(mse, 0.95)


class LSTMAutoencoder(nn.Module):
    """
    Legacy LSTM Autoencoder (added back for comparison).
    """
    def __init__(self, input_dim: int, hidden_dim: int = 64, latent_dim: int = 16, num_layers: int = 2):
        super().__init__()
        self.encoder_lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=0.2 if num_layers > 1 else 0)
        self.encoder_fc   = nn.Linear(hidden_dim, latent_dim)
        self.decoder_fc   = nn.Linear(latent_dim, hidden_dim)
        self.decoder_lstm = nn.LSTM(hidden_dim, hidden_dim, num_layers, batch_first=True, dropout=0.2 if num_layers > 1 else 0)
        self.decoder_out  = nn.Linear(hidden_dim, input_dim)
        self.register_buffer('mse_p5',  torch.tensor(0.0))
        self.register_buffer('mse_p95', torch.tensor(1.0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h, _) = self.encoder_lstm(x)
        latent    = self.encoder_fc(h[-1])
        repeated  = self.decoder_fc(latent).unsqueeze(1).repeat(1, x.shape[1], 1)
        out, _    = self.decoder_lstm(repeated)
        return self.decoder_out(out)

    def anomaly_score(self, x: torch.Tensor) -> np.ndarray:
        self.eval()
        with torch.no_grad():
            mse   = torch.mean((x - self.forward(x)) ** 2, dim=(1, 2))
            score = (mse - self.mse_p5) / (self.mse_p95 - self.mse_p5 + 1e-8)
            return score.clamp(0, 1).cpu().numpy()

    def calibrate(self, normal_tensor: torch.Tensor):
        self.eval()
        with torch.no_grad():
            mse = torch.mean((normal_tensor - self.forward(normal_tensor)) ** 2, dim=(1, 2))
            self.mse_p5  = torch.quantile(mse, 0.05)
            self.mse_p95 = torch.quantile(mse, 0.95)


class SARIMAForecaster:
    """
    Statistical forecasting model using ARIMA(2,1,1) per cell.
    Acts as an independent statistical signal in the anomaly ensemble.
    """
    ORDER = (2, 1, 1)

    def __init__(self):
        self.models = {}

    def fit(self, df: pd.DataFrame, scaler, features: list):
        log.info("Fitting SARIMA forecasters per cell ...")
        cells = df['cell_id'].unique()
        for cell in tqdm(cells, desc="  SARIMA"):
            cell_data = df[df['cell_id'] == cell].sort_values('timestamp')
            if len(cell_data) < 20: continue
            
            # Use a representative KPI (e.g., RSRP or SINR) or an average of all
            # For simplicity, we forecast the first feature (usually RSRP)
            # Optimization: ARIMA doesn't need massive history. Use only the last 500 points.
            y = cell_data[features[0]].values[-500:]
            try:
                model = ARIMA(y, order=self.ORDER)
                self.models[cell] = model.fit()
            except:
                continue
        print("\n\n", flush=True)  # Force a clean line break after tqdm finishes

    def score(self, cell_id: str, current_kpis: np.ndarray) -> float:
        if cell_id not in self.models: return 0.0
        try:
            forecast = self.models[cell_id].forecast(steps=1)[0]
            actual = current_kpis[0] # RSRP
            diff = abs(actual - forecast)
            # Simple scaling to 0-10
            return min(10.0, diff * 2.0)
        except:
            return 0.0

    def save(self, path: Path):
        joblib.dump(self.models, path)

    def load(self, path: Path):
        if path.exists():
            self.models = joblib.load(path)


class TemporalCNN(nn.Module):
    """
    Supervised Sequence Anomaly Classifier.
    Predicts probability of anomaly from a time-series window.
    """
    def __init__(self, input_dim: int):
        super().__init__()
        self.conv1 = nn.Conv1d(input_dim, 64,  3, padding=1)
        self.bn1   = nn.BatchNorm1d(64)
        self.conv2 = nn.Conv1d(64,  128, 3, padding=1)
        self.bn2   = nn.BatchNorm1d(128)
        self.conv3 = nn.Conv1d(128, 128, 3, padding=1)
        self.bn3   = nn.BatchNorm1d(128)
        self.pool  = nn.AdaptiveAvgPool1d(1)
        self.drop  = nn.Dropout(0.3)
        self.anomaly_head = nn.Sequential(
            nn.Linear(128, 32), nn.ReLU(), nn.Linear(32, 1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x.permute(0, 2, 1)
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        x = F.relu(self.bn3(self.conv3(x)))
        x = self.pool(x).squeeze(-1)
        x = self.drop(x)
        return torch.sigmoid(self.anomaly_head(x)).squeeze(-1)

class LSTMPredictor(nn.Module):
    """
    Legacy LSTM Predictor (added back for comparison).
    Predicts future anomaly score from a sliding window.
    """
    def __init__(self, input_dim: int, hidden_dim: int = 64, num_layers: int = 2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_dim, hidden_dim, num_layers, batch_first=True, 
            dropout=0.2 if num_layers > 1 else 0
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h, _) = self.lstm(x)
        return self.head(h[-1])


class GRUPredictor(nn.Module):
    """
    Predicts future anomaly score from a sliding window of KPI values.
    Input:  (batch, seq_len, n_features)
    Output: (batch, 1)  — predicted score [0–10] scaled internally [0,1]
    """
    def __init__(self, input_dim: int, hidden_dim: int = 64, num_layers: int = 2):
        super().__init__()
        self.gru = nn.GRU(
            input_dim, hidden_dim, num_layers, batch_first=True, 
            dropout=0.2 if num_layers > 1 else 0
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, h = self.gru(x)
        return self.head(h[-1])


# ══════════════════════════════════════════════════════════════════════════════
# RULE ENGINE
# ══════════════════════════════════════════════════════════════════════════════
def rule_engine(row: dict) -> dict:
    """
    Evaluates domain-knowledge thresholds against a single KPI row.
    Returns a dict with triggered rules, breach counts, and severity.
    """
    triggered = []
    score = 0

    for kpi, cond in THRESHOLDS.items():
        val = row.get(kpi, None)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        breached = False
        if "min" in cond and val < cond["min"]:
            breached = True
        if "max" in cond and val > cond["max"]:
            breached = True
        if breached:
            triggered.append({"kpi": kpi, "value": round(float(val), 3), "reason": cond["label"]})
            # Weight critical KPIs more
            weight = 2 if kpi in ("RSRP_dBm", "SINR_dB", "call_drop_rate_pct", "HO_success_rate_pct") else 1
            score += weight

    severity_level = min(4, score // 2)
    return {
        "rule_triggered":  len(triggered) > 0,
        "rule_score":      score,
        "rule_severity":   SEVERITY_MAP[severity_level],
        "breached_kpis":   triggered,
    }


# ══════════════════════════════════════════════════════════════════════════════
# BATCH TRAINER  (trains all 4 models)
# ══════════════════════════════════════════════════════════════════════════════
class BatchTrainer:
    """
    Trains all models for both anomaly detection and root cause analysis:
      1. LSTM-Autoencoder + Temporal CNN + LSTM-Predictor (on time_series_kpi.csv)
      2. RCA scaler + Random Forest classifier            (on labeled_incidents.csv)
      3. k-NN similarity index                            (on labeled_incidents.csv)
    """
    def __init__(self, seq_len: int = 16, sample_frac: float = 0.15):
        self.seq_len     = seq_len
        self.sample_frac = sample_frac
        self.device      = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Anomaly detection models
        self.scaler      = StandardScaler()
        self.gru_ae      = None
        self.tcnn        = None
        self.gru_pred    = None

        # RCA models
        self.rca_scaler  = StandardScaler()
        self.le          = LabelEncoder()
        self.xgb         = xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, n_jobs=-1,
            objective="multi:softprob"
        )
        self.knn         = NearestNeighbors(n_neighbors=5, metric="euclidean", n_jobs=-1)
        self.incident_db: list[dict] = []

    # ── Load KPI data ─────────────────────────────────────────────────────────
    def _load_kpi_data(self) -> pd.DataFrame:
        log.info(f"Loading KPI data from {TS_KPI_PATH} ...")
        df = pd.read_csv(TS_KPI_PATH, parse_dates=["timestamp"])
        df = df.dropna(subset=KPI_FEATURES_ANOMALY)
        df = df.sample(frac=self.sample_frac, random_state=42).sort_values("timestamp")
        log.info(f"  Loaded {len(df):,} rows after {self.sample_frac*100:.0f}% sample")
        return df

    # ── Build Sequences (Vectorised with numpy strides) ────────────────────────
    def _build_sequences(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        log.info("  Building sliding-window sequences (vectorised) ...")
        X_scaled = self.scaler.transform(df[KPI_FEATURES_ANOMALY].values)
        y_labels = (df["label"] == "anomaly").astype(np.float32).values
        y_scores = (df["anomaly_score_0_10"].values / 10.0).astype(np.float32)

        Xs, ys_tcnn, ys_lstm = [], [], []
        groups = df.groupby("cell_id")
        for cell_id, group in tqdm(groups, desc="  Sequencing cells", leave=False):
            idx = group.index
            mask = df.index.isin(idx)
            gX = X_scaled[mask]
            gY = y_labels[mask]
            gS = y_scores[mask]
            n  = len(gX) - self.seq_len
            if n <= 0:
                continue

            # Vectorised sliding windows via np.lib.stride_tricks
            shape   = (n, self.seq_len, gX.shape[1])
            strides = (gX.strides[0], gX.strides[0], gX.strides[1])
            windows = np.lib.stride_tricks.as_strided(gX, shape=shape, strides=strides).copy()
            Xs.append(windows)

            # Vectorised label windows
            y_shape   = (n, self.seq_len)
            y_strides = (gY.strides[0], gY.strides[0])
            y_windows = np.lib.stride_tricks.as_strided(gY, shape=y_shape, strides=y_strides)
            ys_tcnn.append((y_windows.sum(axis=1) > 0).astype(np.float32))

            # Future target scores
            ys_lstm.append(gS[self.seq_len:])

        if not Xs:
            return np.empty((0,), dtype=np.float32), np.empty((0,), dtype=np.float32), np.empty((0,), dtype=np.float32)

        log.info(f"  Sequences built: {sum(len(x) for x in Xs):,} total")
        return (
            np.concatenate(Xs).astype(np.float32),
            np.concatenate(ys_tcnn).astype(np.float32),
            np.concatenate(ys_lstm).astype(np.float32),
        )

    # ── Train DL Models ───────────────────────────────────────────────────────
    def _train_dl_models(self, df: pd.DataFrame):
        log.info("Scaling features and building sequences ...")
        self.scaler.fit(df[KPI_FEATURES_ANOMALY].values)
        X_seq, y_seq, y_lstm_seq = self._build_sequences(df)
        
        if len(X_seq) == 0:
            log.error("No sequences built. Check chunk sizes/sample block.")
            return

        split = int(0.85 * len(X_seq))
        X_tr, X_val = X_seq[:split], X_seq[split:]
        y_tr, y_val = y_seq[:split], y_seq[split:]
        yl_tr, yl_val = y_lstm_seq[:split], y_lstm_seq[split:]

        # Create DataLoaders
        batch_size = 256
        
        # LSTM-AE Normal Dataset
        X_tr_normal = X_tr[y_tr == 0]
        normal_loader = DataLoader(
            TensorDataset(torch.FloatTensor(X_tr_normal)), 
            batch_size=batch_size, shuffle=True
        )

        val_normal = X_val[y_val == 0]
        val_loader = DataLoader(
            TensorDataset(torch.FloatTensor(val_normal)), 
            batch_size=batch_size, shuffle=False
        )

        log.info("Training GRU-Autoencoder on NORMAL sequences ...")
        mlflow.start_run(run_name="GRU-AE", nested=True)
        mlflow.log_params({"batch_size": batch_size, "learning_rate": 1e-3, "early_stopping_patience": 4})

        self.gru_ae = GRUAutoencoder(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        optim_ae = torch.optim.Adam(self.gru_ae.parameters(), lr=1e-3)
        es_ae = EarlyStopping(patience=4)
        self.gru_ae.train()
        train_metrics = {}
        val_metrics = {}

        for epoch in range(1, 31):
            self.gru_ae.train()
            epoch_loss = 0.0
            pbar = tqdm(normal_loader, desc=f"  GRU-AE Epoch {epoch:02d}", leave=False)
            for (batch_x,) in pbar:
                batch_x = batch_x.to(self.device)
                optim_ae.zero_grad()
                loss = F.mse_loss(self.gru_ae(batch_x), batch_x)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.gru_ae.parameters(), 1.0)
                optim_ae.step()
                epoch_loss += loss.item() * len(batch_x)
                pbar.set_postfix(loss=f"{loss.item():.5f}")
            epoch_loss /= max(len(X_tr_normal), 1)
            train_metrics[epoch] = epoch_loss

            # Validation loss
            self.gru_ae.eval()
            v_loss = 0.0
            with torch.no_grad():
                for (bx,) in val_loader:
                    bx = bx.to(self.device)
                    v_loss += F.mse_loss(self.gru_ae(bx), bx).item() * len(bx)
            v_loss /= max(len(val_normal), 1)
            val_metrics[epoch] = v_loss

            log.info(f"  GRU-AE Epoch {epoch:02d} — train={epoch_loss:.5f} | val={v_loss:.5f}")
            if es_ae.step(v_loss):
                log.info(f"  ⛔ GRU-AE early stop at epoch {epoch}")
                break
        for ep in train_metrics:
            mlflow.log_metric("train_loss", train_metrics[ep], step=ep)
            mlflow.log_metric("val_loss", val_metrics[ep], step=ep)
        mlflow.log_metric("final_train_loss", epoch_loss)
        mlflow.log_metric("final_val_loss", v_loss)
        if es_ae.stopped:
            mlflow.log_metric("early_stop_epoch", epoch)
        mlflow.end_run()

        # Calibrate GRU-AE
        if len(val_normal) > 0:
            self.gru_ae.eval()
            mse_list = []
            with torch.no_grad():
                for (batch_x,) in val_loader:
                    batch_x = batch_x.to(self.device)
                    mse = torch.mean((batch_x - self.gru_ae(batch_x)) ** 2, dim=(1, 2))
                    mse_list.append(mse.cpu())
            mse_tensor = torch.cat(mse_list)
            self.gru_ae.mse_p5 = torch.quantile(mse_tensor, 0.05).to(self.device)
            self.gru_ae.mse_p95 = torch.quantile(mse_tensor, 0.95).to(self.device)

        # Checkpoint: save immediately
        torch.save(self.gru_ae.state_dict(), MODEL_DIR / "gru_ae.pt")
        log.info("  ✓ GRU-AE checkpointed")

        # Train Legacy LSTM Autoencoder
        log.info("Training Legacy LSTM Autoencoder on NORMAL sequences ...")
        mlflow.start_run(run_name="LSTM-Autoencoder", nested=True)
        mlflow.log_params({"batch_size": batch_size, "learning_rate": 1e-3, "early_stopping_patience": 4})

        self.lstm_ae = LSTMAutoencoder(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        optim_lstm_ae = torch.optim.Adam(self.lstm_ae.parameters(), lr=1e-3)
        es_lstm_ae = EarlyStopping(patience=4)
        lstm_ae_train_metrics, lstm_ae_val_metrics = {}, {}

        for epoch in range(1, 31):
            self.lstm_ae.train()
            epoch_loss = 0.0
            pbar = tqdm(normal_loader, desc=f"  LSTM-AE Epoch {epoch:02d}", leave=False)
            for (batch_x,) in pbar:
                batch_x = batch_x.to(self.device)
                optim_lstm_ae.zero_grad()
                loss = F.mse_loss(self.lstm_ae(batch_x), batch_x)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.lstm_ae.parameters(), 1.0)
                optim_lstm_ae.step()
                epoch_loss += loss.item() * len(batch_x)
                pbar.set_postfix(loss=f"{loss.item():.5f}")
            epoch_loss /= max(len(X_tr_normal), 1)
            lstm_ae_train_metrics[epoch] = epoch_loss

            self.lstm_ae.eval()
            v_loss = 0.0
            with torch.no_grad():
                for (bx,) in val_loader:
                    bx = bx.to(self.device)
                    v_loss += F.mse_loss(self.lstm_ae(bx), bx).item() * len(bx)
            v_loss /= max(len(val_normal), 1)
            lstm_ae_val_metrics[epoch] = v_loss

            log.info(f"  LSTM-AE Epoch {epoch:02d} — train={epoch_loss:.5f} | val={v_loss:.5f}")
            if es_lstm_ae.step(v_loss):
                log.info(f"  ⛔ LSTM-AE early stop at epoch {epoch}")
                break
                
        for ep in lstm_ae_train_metrics:
            mlflow.log_metric("train_loss", lstm_ae_train_metrics[ep], step=ep)
            mlflow.log_metric("val_loss", lstm_ae_val_metrics[ep], step=ep)
        mlflow.log_metric("final_train_loss", epoch_loss)
        mlflow.log_metric("final_val_loss", v_loss)
        if es_lstm_ae.stopped:
            mlflow.log_metric("early_stop_epoch", epoch)
        mlflow.end_run()

        if len(val_normal) > 0:
            self.lstm_ae.calibrate(torch.FloatTensor(val_normal).to(self.device))

        torch.save(self.lstm_ae.state_dict(), MODEL_DIR / "lstm_ae.pt")
        log.info("  ✓ LSTM-AE checkpointed")

        # 2. Train TCNN on all sequences (Supervised)
        log.info("Training Temporal CNN on ALL sequences ...")
        mlflow.start_run(run_name="Temporal-CNN", nested=True)
        mlflow.log_params({"batch_size": batch_size, "learning_rate": 1e-3, "early_stopping_patience": 4})

        tcnn_loader = DataLoader(
            TensorDataset(torch.FloatTensor(X_tr), torch.FloatTensor(y_tr)), 
            batch_size=batch_size, shuffle=True
        )
        tcnn_val_loader = DataLoader(
            TensorDataset(torch.FloatTensor(X_val), torch.FloatTensor(y_val)),
            batch_size=batch_size, shuffle=False
        )

        self.tcnn = TemporalCNN(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        optim_cnn = torch.optim.Adam(self.tcnn.parameters(), lr=1e-3, weight_decay=1e-4)

        n_pos = (y_tr == 1).sum().clip(min=1)
        n_neg = (y_tr == 0).sum().clip(min=1)
        pos_w = torch.tensor(n_neg / n_pos).clamp(0.5, 10.0).to(self.device)
        bce = nn.BCELoss(reduction='none')
        es_tcnn = EarlyStopping(patience=4)
        train_metrics = {}
        val_metrics = {}

        for epoch in range(1, 31):
            self.tcnn.train()
            epoch_loss = 0.0
            pbar = tqdm(tcnn_loader, desc=f"  TCNN Epoch {epoch:02d}", leave=False)
            for batch_x, batch_y in pbar:
                batch_x, batch_y = batch_x.to(self.device), batch_y.to(self.device)
                optim_cnn.zero_grad()
                scores = self.tcnn(batch_x)
                raw_loss = bce(scores, batch_y)
                w = torch.where(batch_y == 1, pos_w, torch.ones_like(batch_y))
                loss = (raw_loss * w).mean()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.tcnn.parameters(), 1.0)
                optim_cnn.step()
                epoch_loss += loss.item() * len(batch_x)
                pbar.set_postfix(loss=f"{loss.item():.5f}")
            epoch_loss /= max(len(X_tr), 1)
            train_metrics[epoch] = epoch_loss

            # Validation loss
            self.tcnn.eval()
            v_loss = 0.0
            with torch.no_grad():
                for bx, by in tcnn_val_loader:
                    bx, by = bx.to(self.device), by.to(self.device)
                    sc = self.tcnn(bx)
                    rl = bce(sc, by)
                    wv = torch.where(by == 1, pos_w, torch.ones_like(by))
                    v_loss += (rl * wv).mean().item() * len(bx)
            v_loss /= max(len(X_val), 1)
            val_metrics[epoch] = v_loss

            log.info(f"  TCNN Epoch {epoch:02d} — train={epoch_loss:.5f} | val={v_loss:.5f}")
            if es_tcnn.step(v_loss):
                log.info(f"  ⛔ TCNN early stop at epoch {epoch}")
                break
        for ep in train_metrics:
            mlflow.log_metric("train_loss", train_metrics[ep], step=ep)
            mlflow.log_metric("val_loss", val_metrics[ep], step=ep)
        mlflow.log_metric("final_train_loss", epoch_loss)
        mlflow.log_metric("final_val_loss", v_loss)
        if es_tcnn.stopped:
            mlflow.log_metric("early_stop_epoch", epoch)
        mlflow.end_run()

        # Checkpoint TCNN
        torch.save(self.tcnn.state_dict(), MODEL_DIR / "tcnn.pt")
        log.info("  ✓ TCNN checkpointed")

        # 3. Train GRU Predictor (Supervised future regression)
        log.info("Training GRU Predictor on ALL sequences ...")
        mlflow.start_run(run_name="GRU-Predictor", nested=True)
        mlflow.log_params({"batch_size": batch_size, "learning_rate": 1e-3, "early_stopping_patience": 4})

        gru_loader = DataLoader(
            TensorDataset(torch.FloatTensor(X_tr), torch.FloatTensor(yl_tr)),
            batch_size=batch_size, shuffle=True
        )
        gru_val_loader = DataLoader(
            TensorDataset(torch.FloatTensor(X_val), torch.FloatTensor(yl_val)),
            batch_size=batch_size, shuffle=False
        )

        self.gru_pred = GRUPredictor(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        optim_pred = torch.optim.Adam(self.gru_pred.parameters(), lr=1e-3)
        mse_loss = nn.MSELoss()
        es_gru = EarlyStopping(patience=4)
        train_metrics = {}
        val_metrics = {}

        for epoch in range(1, 31):
            self.gru_pred.train()
            epoch_loss = 0.0
            pbar = tqdm(gru_loader, desc=f"  GRU-Predictor Epoch {epoch:02d}", leave=False)
            for batch_x, batch_y in pbar:
                batch_x, batch_y = batch_x.to(self.device), batch_y.to(self.device)
                optim_pred.zero_grad()
                preds = self.gru_pred(batch_x).squeeze(-1)
                loss = mse_loss(preds, batch_y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.gru_pred.parameters(), 1.0)
                optim_pred.step()
                epoch_loss += loss.item() * len(batch_x)
                pbar.set_postfix(loss=f"{loss.item():.5f}")
            epoch_loss /= max(len(X_tr), 1)
            train_metrics[epoch] = epoch_loss

            # Validation loss
            self.gru_pred.eval()
            v_loss = 0.0
            with torch.no_grad():
                for bx, by in gru_val_loader:
                    bx, by = bx.to(self.device), by.to(self.device)
                    v_loss += mse_loss(self.gru_pred(bx).squeeze(-1), by).item() * len(bx)
            v_loss /= max(len(X_val), 1)
            val_metrics[epoch] = v_loss

            log.info(f"  GRU Predictor Epoch {epoch:02d} — train={epoch_loss:.5f} | val={v_loss:.5f}")
            if es_gru.step(v_loss):
                log.info(f"  ⛔ GRU-Predictor early stop at epoch {epoch}")
                break
        for ep in train_metrics:
            mlflow.log_metric("train_loss", train_metrics[ep], step=ep)
            mlflow.log_metric("val_loss", val_metrics[ep], step=ep)
        mlflow.log_metric("final_train_loss", epoch_loss)
        mlflow.log_metric("final_val_loss", v_loss)
        if es_gru.stopped:
            mlflow.log_metric("early_stop_epoch", epoch)
        mlflow.end_run()

        # Checkpoint GRU-Predictor
        torch.save(self.gru_pred.state_dict(), MODEL_DIR / "gru_predictor.pt")
        log.info("  ✓ GRU-Predictor checkpointed")

        # 4. Train LSTM Predictor (Legacy comparison)
        log.info("Training Legacy LSTM Predictor on ALL sequences ...")
        mlflow.start_run(run_name="LSTM-Predictor", nested=True)
        mlflow.log_params({"batch_size": batch_size, "learning_rate": 1e-3, "early_stopping_patience": 4})

        self.lstm_pred = LSTMPredictor(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        optim_lstm = torch.optim.Adam(self.lstm_pred.parameters(), lr=1e-3)
        es_lstm = EarlyStopping(patience=4)
        lstm_train_metrics, lstm_val_metrics = {}, {}

        for epoch in range(1, 31):
            self.lstm_pred.train()
            epoch_loss = 0.0
            pbar = tqdm(gru_loader, desc=f"  LSTM-Predictor Epoch {epoch:02d}", leave=False)
            for batch_x, batch_y in pbar:
                batch_x, batch_y = batch_x.to(self.device), batch_y.to(self.device)
                optim_lstm.zero_grad()
                preds = self.lstm_pred(batch_x).squeeze(-1)
                loss = mse_loss(preds, batch_y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.lstm_pred.parameters(), 1.0)
                optim_lstm.step()
                epoch_loss += loss.item() * len(batch_x)
                pbar.set_postfix(loss=f"{loss.item():.5f}")
            epoch_loss /= max(len(X_tr), 1)
            lstm_train_metrics[epoch] = epoch_loss

            self.lstm_pred.eval()
            v_loss = 0.0
            with torch.no_grad():
                for bx, by in gru_val_loader:
                    bx, by = bx.to(self.device), by.to(self.device)
                    v_loss += mse_loss(self.lstm_pred(bx).squeeze(-1), by).item() * len(bx)
            v_loss /= max(len(X_val), 1)
            lstm_val_metrics[epoch] = v_loss

            log.info(f"  LSTM Predictor Epoch {epoch:02d} — train={epoch_loss:.5f} | val={v_loss:.5f}")
            if es_lstm.step(v_loss):
                log.info(f"  ⛔ LSTM-Predictor early stop at epoch {epoch}")
                break
        
        for ep in lstm_train_metrics:
            mlflow.log_metric("train_loss", lstm_train_metrics[ep], step=ep)
            mlflow.log_metric("val_loss", lstm_val_metrics[ep], step=ep)
        mlflow.log_metric("final_train_loss", epoch_loss)
        mlflow.log_metric("final_val_loss", v_loss)
        if es_lstm.stopped:
            mlflow.log_metric("early_stop_epoch", epoch)
        mlflow.end_run()
        
        torch.save(self.lstm_pred.state_dict(), MODEL_DIR / "lstm_predictor.pt")
        log.info("  ✓ LSTM-Predictor checkpointed")

        # Save scaler + upload all artifacts to MLflow
        joblib.dump(self.scaler, SCALER_PATH)
        
        mlflow.log_artifact(str(MODEL_DIR / "gru_ae.pt"), artifact_path="models")
        mlflow.log_artifact(str(MODEL_DIR / "lstm_ae.pt"), artifact_path="models")
        mlflow.log_artifact(str(MODEL_DIR / "tcnn.pt"), artifact_path="models")
        mlflow.log_artifact(str(MODEL_DIR / "gru_predictor.pt"), artifact_path="models")
        mlflow.log_artifact(str(MODEL_DIR / "lstm_predictor.pt"), artifact_path="models")
        mlflow.log_artifact(str(SCALER_PATH), artifact_path="scalers")

        log.info("  DL Models saved [OK]")

    # ── Load labeled incidents ────────────────────────────────────────────────
    def _load_incidents(self) -> pd.DataFrame:
        global KPI_FEATURES_RCA
        log.info(f"Loading labeled incidents from {INCIDENTS_PATH} ...")
        df = pd.read_csv(INCIDENTS_PATH)

        # Auto-detect which KPI columns are actually present
        available = [c for c in KPI_FEATURES_ANOMALY if c in df.columns]
        KPI_FEATURES_RCA = available
        log.info(f"  Using {len(KPI_FEATURES_RCA)} RCA features: {KPI_FEATURES_RCA}")

        df = df.dropna(subset=KPI_FEATURES_RCA + ["root_cause"])
        log.info(f"  {len(df):,} incidents loaded | {df['root_cause'].nunique()} unique causes")
        return df

    # ── Train RCA classifiers (XGBoost + RF) ──────────────────────────────────
    def _train_classifier(self, df: pd.DataFrame):
        log.info("Training XGBoost RCA classifier ...")
        mlflow.start_run(run_name="RCA_XGBoost", nested=True)
        
        X = self.rca_scaler.fit_transform(df[KPI_FEATURES_RCA].values)
        y = self.le.fit_transform(df["root_cause"].values)

        split = int(0.8 * len(X))
        X_tr, X_val = X[:split], X[split:]
        y_tr, y_val = y[:split], y[split:]

        log.info(f"  Fitting XGBoost on {len(X_tr):,} samples ...")
        self.xgb.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        y_pred_xgb = self.xgb.predict(X_val)

        report_xgb = classification_report(y_val, y_pred_xgb, target_names=self.le.classes_, zero_division=0, output_dict=True)
        log.info(f"  XGBoost Accuracy: {report_xgb['accuracy']:.4f}")

        mlflow.log_metric("accuracy", report_xgb["accuracy"])
        mlflow.log_param("n_estimators", 300)
        mlflow.log_param("max_depth", 6)
        mlflow.end_run()

        # ── Random Forest (Legacy comparison) ──
        log.info("Training Legacy Random Forest classifier for comparison ...")
        mlflow.start_run(run_name="RCA_RandomForest", nested=True)
        
        self.rf = RandomForestClassifier(n_estimators=300, max_depth=6, random_state=42, n_jobs=-1)
        self.rf.fit(X_tr, y_tr)
        y_pred_rf = self.rf.predict(X_val)
        
        report_rf = classification_report(y_val, y_pred_rf, target_names=self.le.classes_, zero_division=0, output_dict=True)
        log.info(f"  Random Forest Accuracy: {report_rf['accuracy']:.4f}")
        
        mlflow.log_metric("accuracy", report_rf["accuracy"])
        mlflow.log_param("n_estimators", 300)
        mlflow.log_param("max_depth", 6)
        mlflow.end_run()

        # ── SHAP Explainability (on XGBoost) ──────────────────────────────────
        log.info("  Computing SHAP explainer for XGBoost ...")
        shap_sample = X_tr[:min(100, len(X_tr))]
        explainer = shap.TreeExplainer(self.xgb)
        # Pre-compute
        _ = explainer.shap_values(shap_sample[:5])
        joblib.dump(explainer, MODEL_DIR / "shap_explainer.joblib")

        # ── Persist models ────────────────────────────────────────────────────
        log.info("  Saving RCA models to disk ...")
        joblib.dump(self.xgb,        XGB_PATH)
        joblib.dump(self.rca_scaler, RCA_SCALER_PATH)
        joblib.dump(self.le,         LABEL_ENC_PATH)
        joblib.dump(KPI_FEATURES_RCA, MODEL_DIR / "rca_kpi_features.joblib")
        
        log.info("  Uploading RCA artifacts to MLflow ...")
        mlflow.log_artifact(str(RCA_SCALER_PATH), artifact_path="scalers")
        mlflow.log_artifact(str(LABEL_ENC_PATH), artifact_path="encoders")
        # Skipping large model artifacts (XGB, RF, SHAP) to prevent Windows Defender hangs

    # ── Build k-NN similarity index ───────────────────────────────────────────
    def _build_knn_index(self, df: pd.DataFrame):
        log.info("Building k-NN similarity index ...")
        X = self.rca_scaler.transform(df[KPI_FEATURES_RCA].values)
        self.knn.fit(X)

        self.incident_db = []
        for _, row in df.iterrows():
            self.incident_db.append({
                "incident_id":    str(row.get("incident_id", "")),
                "root_cause":     str(row.get("root_cause", "")),
                "issue_type":     str(row.get("issue_type", "")),
                "severity":       str(row.get("severity", "")),
                "resolution_hours": row.get("resolution_hours", None),
                "recommended_solution": str(row.get("recommended_solution", "")),
                "kpi_snapshot": {
                    k: round(float(row[k]), 3)
                    for k in KPI_FEATURES_RCA if pd.notna(row.get(k, np.nan))
                },
            })

        joblib.dump(self.knn,          KNN_PATH)
        joblib.dump(self.incident_db,  INCIDENT_DB_PATH)
        
        # Log to MLflow
        mlflow.log_artifact(str(KNN_PATH), artifact_path="rca")
        mlflow.log_artifact(str(INCIDENT_DB_PATH), artifact_path="rca")
        
        log.info(f"  k-NN index built on {len(self.incident_db):,} incidents -> {KNN_PATH}")

    # ── Run full training ─────────────────────────────────────────────────────
    def run(self):
        log.info("=" * 60)
        log.info("BATCH TRAINING — DetectionAgent")
        log.info("=" * 60)

        mlflow.set_tracking_uri("sqlite:///mlflow_tracking.db")
        mlflow.set_experiment("QoSBuddy_Pipeline")
        with mlflow.start_run(run_name="Full_Pipeline_Training"):
            mlflow.log_param("seq_len", self.seq_len)
            mlflow.log_param("sample_frac", self.sample_frac)

            # Phase A: Anomaly detection models
            log.info("-" * 60)
            log.info("Phase A: Deep Learning Anomaly Models")
            log.info("-" * 60)
            df_kpi = self._load_kpi_data()
            self._train_dl_models(df_kpi)

            # Phase A2: SARIMA statistical forecasters
            log.info("-" * 60)
            log.info("Phase A2: SARIMA Statistical Forecasters")
            log.info("-" * 60)
            mlflow.start_run(run_name="SARIMA-Forecaster", nested=True)
            sarima = SARIMAForecaster()
            sarima.fit(df_kpi, self.scaler, KPI_FEATURES_ANOMALY)
            log.info(f"  Saving {len(sarima.models)} SARIMA models to disk (may take a moment) ...")
            sarima.save(SARIMA_PATH)
            log.info("  ✓ SARIMA models saved locally.")

            log.info("  Uploading SARIMA parameters to MLflow ...")
            mlflow.log_param("arima_order", str(SARIMAForecaster.ORDER))
            mlflow.log_metric("cells_fitted", len(sarima.models))
            mlflow.end_run()
            log.info("  ✓ SARIMA Phase Complete.")
            sys.stdout.flush()
    
            # Phase A3: Isolation Forest
            log.info("-" * 60)
            log.info("Phase A3: Isolation Forest (Legacy comparison)")
            log.info("-" * 60)
            mlflow.start_run(run_name="IsolationForest-Anomaly", nested=True)
            self.iso = IsolationForest(n_estimators=100, contamination=0.05, random_state=42, n_jobs=-1)
            # Flatten KPI for isolation forest
            X_iso = df_kpi[KPI_FEATURES_ANOMALY].fillna(0).values
            X_iso = self.scaler.transform(X_iso)
            log.info(f"  Fitting Isolation Forest on {len(X_iso):,} samples ...")
            self.iso.fit(X_iso)
            log.info("  ✓ Isolation Forest trained.")
            mlflow.log_param("n_estimators", 100)
            mlflow.log_param("contamination", 0.05)
            mlflow.end_run()

            # Phase B: RCA models
            log.info("-" * 60)
            log.info("Phase B: Root Cause Analysis Models")
            log.info("-" * 60)
            df_inc = self._load_incidents()
            self._train_classifier(df_inc)
            self._build_knn_index(df_inc)
    
            log.info("=" * 60)
            log.info("All models trained [OK]")
            log.info("=" * 60)


# ══════════════════════════════════════════════════════════════════════════════
# RCA ENGINE  (inline, used by the stream inferencer)
# ══════════════════════════════════════════════════════════════════════════════
class RCAEngine:
    """
    Loads trained RCA models and diagnoses a single anomaly event.
    """
    def __init__(self):
        global KPI_FEATURES_RCA
        log.info("Loading RCA models ...")
        required = [XGB_PATH, RCA_SCALER_PATH, LABEL_ENC_PATH, KNN_PATH, INCIDENT_DB_PATH]
        if not all(p.exists() for p in required):
            raise FileNotFoundError("RCA models (XGBoost) not found. Run with --mode train first.")

        self.xgb          = joblib.load(XGB_PATH)
        self.rca_scaler   = joblib.load(RCA_SCALER_PATH)
        self.le           = joblib.load(LABEL_ENC_PATH)
        self.knn          = joblib.load(KNN_PATH)
        self.incident_db  = joblib.load(INCIDENT_DB_PATH)

        # Optimization for inference
        self.knn.n_jobs = 1

        # SHAP explainer
        shap_path = MODEL_DIR / "shap_explainer.joblib"
        try:
            self.shap_explainer = joblib.load(shap_path) if shap_path.exists() else None
        except Exception as e:
            log.warning(f"Could not load SHAP explainer (likely Python version mismatch): {e}")
            self.shap_explainer = None

        # Restore the exact feature list used during training
        feat_path = MODEL_DIR / "rca_kpi_features.joblib"
        if feat_path.exists():
            KPI_FEATURES_RCA = joblib.load(feat_path)
            log.info(f"  Restored {len(KPI_FEATURES_RCA)} RCA features from saved model")
        log.info("  RCA models loaded [OK] (n_jobs=1 for single-sample inference)")

    def _extract_kpi_vector(self, kpi_snapshot: dict) -> np.ndarray | None:
        vec = []
        for feat in KPI_FEATURES_RCA:
            v = kpi_snapshot.get(feat, None)
            vec.append(float(v) if v is not None else np.nan)
        arr = np.array(vec, dtype=np.float64)
        if np.isnan(arr).all():
            return None
        arr = np.where(np.isnan(arr), 0.0, arr)
        return arr

    def _classify(self, x_raw: np.ndarray) -> tuple[list[dict], list[dict]]:
        x_scaled = self.rca_scaler.transform(x_raw.reshape(1, -1))
        proba    = self.xgb.predict_proba(x_scaled)[0]
        classes  = self.le.classes_

        ranked = sorted(
            [{"cause": str(c), "probability": round(float(p), 4)} for c, p in zip(classes, proba)],
            key=lambda d: d["probability"],
            reverse=True,
        )

        # SHAP feature contributions — cached per predicted cause to avoid
        # recomputing for every event with the same top cause
        top_cause = ranked[0]["cause"]
        kpi_contributions = []
        if self.shap_explainer is not None:
            if not hasattr(self, '_shap_cache'):
                self._shap_cache = {}
            if top_cause in self._shap_cache:
                kpi_contributions = self._shap_cache[top_cause]
            else:
                try:
                    top_class_idx = self.le.transform([top_cause])[0]
                    sv = self.shap_explainer.shap_values(x_scaled, check_additivity=False)
                    if isinstance(sv, list):
                        vals = sv[top_class_idx][0]
                    else:
                        vals = sv[0]
                    contrib = sorted(
                        [{"kpi": feat, "impact": round(float(v), 4)}
                         for feat, v in zip(KPI_FEATURES_RCA, vals)],
                        key=lambda d: abs(d["impact"]), reverse=True,
                    )
                    kpi_contributions = contrib[:5]
                    self._shap_cache[top_cause] = kpi_contributions
                except Exception:
                    pass  # degrade gracefully

        return ranked, kpi_contributions

    def _find_similar(self, x_raw: np.ndarray, top_k: int = 3) -> list[dict]:
        x_scaled  = self.rca_scaler.transform(x_raw.reshape(1, -1))
        distances, indices = self.knn.kneighbors(x_scaled, n_neighbors=top_k)

        dists = distances[0]
        ref_scale = max(float(np.mean(dists)), 0.5)

        similar = []
        for dist, idx in zip(dists, indices[0]):
            inc = self.incident_db[idx]
            sim_pct = round(float(np.clip(np.exp(-dist / ref_scale) * 100, 1, 99)), 1)
            similar.append({
                "incident_id":        inc["incident_id"],
                "root_cause":         inc["root_cause"],
                "issue_type":         inc["issue_type"],
                "severity":           inc["severity"],
                "resolution_hours":   inc["resolution_hours"],
                "recommended_solution": inc["recommended_solution"],
                "kpi_distance":       round(float(dist), 4),
                "similarity_pct":     sim_pct,
            })
        return similar

    def _rule_override(self, kpi_snapshot: dict, rule_breaches: list) -> str | None:
        breached_kpis = {b["kpi"] for b in rule_breaches}

        rsrp  = kpi_snapshot.get("RSRP_dBm", 0)
        sinr  = kpi_snapshot.get("SINR_dB",  99)
        prb   = kpi_snapshot.get("PRB_util_DL_pct", 0)
        lat   = kpi_snapshot.get("latency_ms", 0)
        ho_sr = kpi_snapshot.get("HO_success_rate_pct", 100)
        cdr   = kpi_snapshot.get("call_drop_rate_pct", 0)

        if rsrp < -115 and sinr < 0:
            return "Poor RSRP coverage"
        if sinr < -3 and "SINR_dB" in breached_kpis and prb < 70:
            return "High interference (SINR<0)"
        if ho_sr < 70 and cdr > 4:
            return "HO failure"
        if prb > 90 and lat > 60:
            return "PRB saturation"
        if lat > 100 and prb < 70:
            return "Transport congestion"
        if ho_sr < 75 and sinr > 5:
            return "Missing neighbor relation"
        return None

    def diagnose(self, kpi_snapshot: dict, rule_result: dict,
                 neighbour_escalated: bool = False) -> dict:
        x_raw = self._extract_kpi_vector(kpi_snapshot)

        if x_raw is None:
            return {
                "status": "error",
                "reason": "No KPI data in event",
            }

        # 1 — XGBoost ranked causes + SHAP explainability
        ranked_causes, kpi_contributions = self._classify(x_raw)
        top_cause     = ranked_causes[0]["cause"]
        top_prob      = ranked_causes[0]["probability"]

        # 2 — Rule override
        rule_breaches = rule_result.get("breached_kpis", [])
        override = self._rule_override(kpi_snapshot, rule_breaches)
        if override and override != top_cause:
            override_entry = {"cause": override, "probability": round(min(1.0, top_prob + 0.15), 4)}
            ranked_causes  = [override_entry] + [r for r in ranked_causes if r["cause"] != override]
            top_cause      = override
            top_prob       = override_entry["probability"]
            used_override  = True
        else:
            used_override  = False

        # 3 — Solution + tags
        solution = CAUSE_TO_SOLUTION.get(top_cause, "Manual investigation required")
        tags     = CAUSE_TO_TAG.get(top_cause, ["unknown"])

        # 4 — Similar incidents
        similar = self._find_similar(x_raw, top_k=3)

        # 5 — Overall RCA confidence
        confidence = round(top_prob * 100, 1)

        # 6 — Neighbour escalation bonus
        cluster_tags = []
        if neighbour_escalated:
            confidence = round(min(99.0, confidence + 12.0), 1)
            cluster_tags = ["cluster_event", "multi_cell"]
            single_cell_causes = {"PCI collision", "Bad tilt/azimuth", "SRVCC failure",
                                   "Wrong codec", "Massive MIMO config issue"}
            if top_cause in single_cell_causes and len(ranked_causes) > 1:
                for alt in ranked_causes[1:]:
                    if alt["cause"] not in single_cell_causes:
                        top_cause = alt["cause"]
                        tags      = CAUSE_TO_TAG.get(top_cause, tags)
                        solution  = CAUSE_TO_SOLUTION.get(top_cause, solution)
                        break

        return {
            "status":              "ok",
            "primary_cause":       top_cause,
            "confidence_pct":      confidence,
            "rca_tags":            tags + cluster_tags,
            "used_rule_override":  used_override,
            "neighbour_escalated": neighbour_escalated,
            "ranked_causes":       ranked_causes[:8],
            "kpi_contributions":   kpi_contributions,
            "recommended_solution": solution,
            "similar_incidents":   similar,
        }


# ══════════════════════════════════════════════════════════════════════════════
# STREAM INFERENCER  (anomaly detection + inline RCA)
# ══════════════════════════════════════════════════════════════════════════════
class StreamInferencer:
    """
    Replays time_series_kpi.csv row-by-row (simulating real-time feed).
    For each row:
      1. Rule engine fires
      2. GRU-AE computes reconstruction error
      3. Temporal CNN classifies anomaly probability
      4. GRU Predictor forecasts future anomaly score
      5. Neighbour correlation check
      6. Fuse signals → anomaly decision
      7. If anomaly → inline RCA (XGBoost + SHAP + k-NN)
      8. Emit combined event to rca_feed.jsonl
    """
    def __init__(self, seq_len: int = 16, stream_delay: float = 0.0,
                 cell_filter: str = None, chunk_size: int = 500):
        self.seq_len      = seq_len
        self.stream_delay = stream_delay
        self.cell_filter  = cell_filter
        self.chunk_size   = chunk_size
        self.device       = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Numpy Ring buffers per cell for DL models
        self.cell_windows: dict[str, dict] = {}

        # Neighbour correlation state
        self.ts_anomaly_cells: OrderedDict[str, set] = OrderedDict()
        self.neighbour_map: dict[str, list] = self._load_neighbour_map()

        # Stats
        self.stats = {"processed": 0, "anomalies": 0, "rca_diagnosed": 0, "critical_escalations": 0}
        self._cause_counts: dict[str, int] = {}  # track top causes for summary
        self._last_progress = 0  # for periodic progress logging

        self._load_models()

    def _load_models(self):
        log.info("Loading anomaly detection models (GRU-AE, TCNN, GRU-Pred) ...")
        ae_path = MODEL_DIR / "gru_ae.pt"
        tcnn_path = MODEL_DIR / "tcnn.pt"
        pred_path = MODEL_DIR / "gru_predictor.pt"
        
        if not SCALER_PATH.exists() or not ae_path.exists() or not tcnn_path.exists() or not pred_path.exists():
            raise FileNotFoundError("Anomaly models not found. Run with --mode train first.")

        self.scaler = joblib.load(SCALER_PATH)

        self.gru_ae = GRUAutoencoder(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        self.gru_ae.load_state_dict(torch.load(ae_path, map_location=self.device))
        self.gru_ae.eval()

        self.tcnn = TemporalCNN(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        self.tcnn.load_state_dict(torch.load(tcnn_path, map_location=self.device))
        self.tcnn.eval()

        self.gru_pred = GRUPredictor(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        self.gru_pred.load_state_dict(torch.load(pred_path, map_location=self.device))
        self.gru_pred.eval()

        log.info("  DL Anomaly models loaded [OK]")

        # Load SARIMA forecasters
        self.sarima = SARIMAForecaster()
        self.sarima.load(SARIMA_PATH)

        # Load RCA engine
        self.rca_engine = RCAEngine()

    def _load_neighbour_map(self) -> dict[str, list]:
        topo_path = DATA_DIR / "cell_topology.csv"
        if not topo_path.exists():
            log.warning("cell_topology.csv not found - neighbour correlation disabled")
            return {}
        try:
            df = pd.read_csv(topo_path)
            nb_map = {}
            for _, r in df.iterrows():
                cell = str(r.get("cell_id", ""))
                raw  = str(r.get("neighbor_cells", ""))
                nb_map[cell] = [n.strip() for n in raw.split(";") if n.strip()]
            log.info(f"  Neighbour map loaded: {len(nb_map)} cells")
            return nb_map
        except Exception as e:
            log.warning(f"Could not load neighbour map: {e}")
            return {}

    def _neighbour_vote(self, cell_id: str, timestamp: str, is_anomaly: bool) -> bool:
        if timestamp not in self.ts_anomaly_cells:
            self.ts_anomaly_cells[timestamp] = set()
            self.ts_anomaly_cells.move_to_end(timestamp)
        bucket = self.ts_anomaly_cells[timestamp]
        
        if is_anomaly:
            bucket.add(cell_id)
        while len(self.ts_anomaly_cells) > 5:
            self.ts_anomaly_cells.popitem(last=False)
            
        if not is_anomaly:
            return False
        neighbours = self.neighbour_map.get(cell_id, [])
        if not neighbours:
            return False
        anomalous_neighbours = sum(1 for nb in neighbours if nb in bucket)
        return anomalous_neighbours >= 2

    def _update_buffer(self, cell_id: str, x_scaled: np.ndarray) -> np.ndarray | None:
        if cell_id not in self.cell_windows:
            self.cell_windows[cell_id] = {
                "buffer": np.zeros((self.seq_len, len(x_scaled)), dtype=np.float32),
                "ptr": 0,
                "count": 0
            }
        state = self.cell_windows[cell_id]
        state["buffer"][state["ptr"]] = x_scaled
        state["ptr"] = (state["ptr"] + 1) % self.seq_len
        state["count"] += 1

        if state["count"] >= self.seq_len:
            return np.roll(state["buffer"], -state["ptr"], axis=0)
        return None

    def _fuse_signals(self, rule: dict, ae_score: float | None,
                      tcnn_score: float | None, pred_score: float | None,
                      sarima_score: float | None = None,
                      neighbour_escalate: bool = False) -> dict:
        votes = 0
        if rule["rule_triggered"]: votes += 1
        if ae_score is not None and ae_score > 5.0: votes += 1
        if tcnn_score is not None and tcnn_score > 5.0: votes += 1
        if pred_score is not None and pred_score > 5.0: votes += 1
        if sarima_score is not None and sarima_score > 5.0: votes += 1

        # Weighted combination (5 signals now)
        combined_score = round(
            (rule["rule_score"]       * 0.30) +
            ((ae_score or 0)         * 0.18) +
            ((tcnn_score or 0)       * 0.25) +
            ((pred_score or 0)       * 0.12) +
            ((sarima_score or 0)     * 0.15), 3
        )

        if votes == 0:
            final_label = "normal"
        elif votes == 1:
            final_label = "low"
        elif votes == 2:
            final_label = "medium"
        elif votes <= 4:
            final_label = "high"
        else:  # votes == 5
            final_label = "critical"

        # Escalation bonus
        if final_label == "high" and neighbour_escalate:
            final_label = "critical"

        return {
            "votes":               votes,
            "combined_score":      combined_score,
            "final_label":         final_label,
            "is_anomaly":          final_label != "normal",
            "neighbour_escalated": neighbour_escalate,
        }

    def _emit_console(self, event: dict):
        sev = event.get("anomaly_severity", "low").upper()
        rca = event.get("rca", {})
        cause = rca.get("primary_cause", "?")
        conf  = rca.get("confidence_pct", 0)

        if sev in ("HIGH", "CRITICAL"):
            icon = "[!!]"
        elif sev == "MEDIUM":
            icon = "[! ]"
        elif sev == "LOW":
            icon = "[~ ]"
        else:
            icon = "[OK]"

        log.info(
            f"{icon} [{sev:<8s}] {event['cell_id']:<14s} | "
            f"cause='{cause}' | conf={conf:.1f}% | "
            f"score={event.get('anomaly_score', 0):.2f}"
        )

    def run(self):
        log.info("=" * 60)
        log.info("LIVE STREAM INFERENCE — DetectionAgent")
        log.info(f"  Feed output -> {RCA_FEED}")
        log.info("=" * 60)

        # Clear previous feed
        RCA_FEED.write_text("")

        with open(RCA_FEED, "a", encoding="utf-8") as feed_file:
            reader = pd.read_csv(
                TS_KPI_PATH,
                parse_dates=["timestamp"],
                chunksize=self.chunk_size,
            )
            t_start = time.time()

            for chunk in reader:
                chunk = chunk.dropna(subset=KPI_FEATURES_ANOMALY)
                if self.cell_filter:
                    chunk = chunk[chunk["cell_id"] == self.cell_filter]
                if chunk.empty:
                    continue

                # ── Extract Batch Arrays ──
                X_chunk = self.scaler.transform(chunk[KPI_FEATURES_ANOMALY].values)
                records = chunk.to_dict("records")
                
                valid_sequences = []
                valid_indices = []
                
                for i, row in enumerate(records):
                    self.stats["processed"] += 1
                    cell_id = str(row["cell_id"])
                    
                    # Native Ring Buffer Extraction
                    seq = self._update_buffer(cell_id, X_chunk[i])
                    if seq is not None:
                        valid_sequences.append(seq)
                        valid_indices.append(i)
                
                # ── Batched DL Inference ──
                ae_scores = [None] * len(records)
                tcnn_scores = [None] * len(records)
                pred_scores = [None] * len(records)
                
                if valid_sequences:
                    batch_tensor = torch.tensor(np.array(valid_sequences), dtype=torch.float32).to(self.device)
                    with torch.no_grad():
                        ae_batch = self.gru_ae.anomaly_score(batch_tensor) * 10.0
                        tcnn_batch = self.tcnn(batch_tensor).squeeze(-1).cpu().numpy() * 10.0
                        pred_batch = self.gru_pred(batch_tensor).squeeze(-1).cpu().numpy() * 10.0
                        
                    for j, original_idx in enumerate(valid_indices):
                        ae_scores[original_idx] = round(float(ae_batch[j]), 3)
                        tcnn_scores[original_idx] = round(float(tcnn_batch[j]), 3)
                        pred_scores[original_idx] = round(float(pred_batch[j]), 3)

                # ── Fusion & Emission Spooling ──

                for i, row in enumerate(records):
                    rule_result = rule_engine(row)
                    ae_score = ae_scores[i]
                    tcnn_score = tcnn_scores[i]
                    pred_score = pred_scores[i]

                    # SARIMA forecast-based anomaly score
                    cell_id = str(row["cell_id"])
                    sarima_score = self.sarima.score(cell_id, X_chunk[i])

                    pre_anomaly = (
                        rule_result["rule_triggered"] or 
                        (ae_score is not None and ae_score > 5.0) or
                        (tcnn_score is not None and tcnn_score > 5.0) or
                        (pred_score is not None and pred_score > 5.0) or
                        (sarima_score is not None and sarima_score > 5.0)
                    )
                    neighbour_escalate = self._neighbour_vote(
                        cell_id, str(row["timestamp"]), pre_anomaly
                    )

                    fusion = self._fuse_signals(
                        rule_result, ae_score, tcnn_score, pred_score,
                        sarima_score, neighbour_escalate
                    )

                    if fusion["is_anomaly"]:
                        self.stats["anomalies"] += 1
                    if fusion.get("neighbour_escalated"):
                        self.stats["critical_escalations"] += 1

                    if fusion["is_anomaly"]:
                        kpi_snapshot = {
                            k: round(float(row[k]), 3)
                            for k in KPI_FEATURES_ANOMALY
                            if k in row and pd.notna(row[k])
                        }

                        # Run RCA diagnosis
                        rca_diagnosis = self.rca_engine.diagnose(
                            kpi_snapshot=kpi_snapshot,
                            rule_result=rule_result,
                            neighbour_escalated=fusion.get("neighbour_escalated", False),
                        )

                        # Build combined event
                        event = {
                            "rca_event_id":      f"RCA-{self.stats['anomalies']:07d}",
                            "agent":             "DetectionAgent",
                            "phase":             "stream",
                            "processed_at":      datetime.now(timezone.utc).isoformat(),
                            "source_event_id":   f"EVT-{self.stats['processed']:07d}",
                            "timestamp":         str(row["timestamp"]),
                            "cell_id":           str(row["cell_id"]),
                            "site_id":           str(row.get("site_id", "") or ""),
                            "region":            str(row.get("region", "") or ""),
                            "vendor":            str(row.get("vendor", "") or ""),
                            "nr_band":           str(row.get("nr_band", "") or ""),
                            "network_slice":     str(row.get("network_slice", "") or ""),
                            "anomaly_severity":  fusion["final_label"],
                            "anomaly_score":     fusion["combined_score"],
                            "kpi_snapshot":      kpi_snapshot,
                            "rule_engine":       rule_result,
                            "dl_anomaly_models": {
                                "gru_ae_score_0_10": ae_score,
                                "tcnn_prob_0_10":     tcnn_score,
                                "gru_pred_0_10":     pred_score,
                                "sarima_score_0_10":  sarima_score,
                                "ready":              ae_score is not None,
                            },
                            "fusion":            fusion,
                            "neighbour_escalated": fusion.get("neighbour_escalated", False),
                            "rca":               rca_diagnosis,
                            "ground_truth_label": str(row.get("label", "unknown") or "unknown"),
                        }

                        # Instantly write to disk so dashboard updates without batch delays
                        feed_file.write(json.dumps(event, default=str) + "\n")
                        feed_file.flush()
                        self._emit_console(event)
                        self.stats["rca_diagnosed"] += 1
                        # Track cause for summary
                        pc = rca_diagnosis.get("primary_cause", "unknown")
                        self._cause_counts[pc] = self._cause_counts.get(pc, 0) + 1

                if self.stream_delay > 0:
                    time.sleep(self.stream_delay)

                # Periodic progress logging every 5K rows
                if self.stats["processed"] - self._last_progress >= 5_000:
                    self._last_progress = self.stats["processed"]
                    elapsed = time.time() - t_start
                    rate = self.stats["processed"] / max(elapsed, 0.1)
                    anom_pct = (self.stats["anomalies"] / max(self.stats["processed"], 1)) * 100
                    log.info(
                        f"  ▶ Progress: {self.stats['processed']:>10,} rows | "
                        f"{self.stats['anomalies']:,} anomalies ({anom_pct:.1f}%) | "
                        f"{self.stats['critical_escalations']} escalations | "
                        f"{rate:,.0f} rows/s"
                    )

        # ── Final Summary ──
        elapsed = time.time() - t_start
        total = self.stats["processed"]
        anom = self.stats["anomalies"]
        diag = self.stats["rca_diagnosed"]
        crit = self.stats["critical_escalations"]
        anom_pct = (anom / max(total, 1)) * 100
        rate = total / max(elapsed, 0.1)

        # Track top cause from events
        top_causes = sorted(self._cause_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        log.info("")
        log.info("═" * 60)
        log.info("  STREAMING SUMMARY")
        log.info("═" * 60)
        log.info(f"  Rows processed:     {total:>12,}")
        log.info(f"  Anomalies detected: {anom:>12,}  ({anom_pct:.1f}%)")
        log.info(f"  RCA diagnosed:      {diag:>12,}")
        log.info(f"  Critical escal.:    {crit:>12,}")
        log.info(f"  Elapsed time:       {elapsed:>11.1f}s")
        log.info(f"  Throughput:         {rate:>10,.0f} rows/s")
        if top_causes:
            log.info(f"  Top causes:")
            for cause, cnt in top_causes:
                pct = (cnt / max(diag, 1)) * 100
                log.info(f"    {cause:<35s} {cnt:>6,} ({pct:.1f}%)")
        log.info(f"  Feed written -> {RCA_FEED}")
        log.info("═" * 60)


# ══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser(description="QoSBuddy - DetectionAgent (Anomaly + RCA)")
    p.add_argument("--mode",        choices=["train","stream","all"], default="all",
                   help="train: batch training only | stream: inference only | all: both (default)")
    p.add_argument("--sample-frac", type=float, default=0.15,
                   help="Fraction of KPI CSV to use for training (default 0.15)")
    p.add_argument("--seq-len",     type=int,   default=16,
                   help="LSTM sequence length in timesteps (default 16 = 4h @ 15min)")
    p.add_argument("--stream-delay",type=float, default=0.0,
                   help="Seconds to wait between streamed rows (default 0 = max speed)")
    p.add_argument("--cell",        type=str,   default=None,
                   help="Filter stream to a specific cell_id (optional)")
    p.add_argument("--chunk-size",  type=int,   default=10,
                   help="CSV chunk size for streaming (default 10)")
    return p.parse_args()


def main():
    args = parse_args()
    log.info("QoSBuddy DetectionAgent starting")
    log.info(f"  mode={args.mode} | seq_len={args.seq_len} | sample_frac={args.sample_frac}")

    if args.mode in ("train", "all"):
        trainer = BatchTrainer(seq_len=args.seq_len, sample_frac=args.sample_frac)
        trainer.run()

    if args.mode in ("stream", "all"):
        inferencer = StreamInferencer(
            seq_len=args.seq_len,
            stream_delay=args.stream_delay,
            cell_filter=args.cell,
            chunk_size=args.chunk_size,
        )
        inferencer.run()


if __name__ == "__main__":
    main()
