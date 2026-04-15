"""
QoSBuddy -- DetectionAgent
======================================================
Unified anomaly detection and root-cause analysis agent.

Pipeline:
  1. BATCH TRAINING   — trains Isolation Forest + LSTM (anomaly detection)
                        and RF classifier + k-NN index (root cause analysis)
                        on historical CSV data.
  2. LIVE INFERENCE   — streams time_series_kpi.csv row-by-row,
                        runs rule engine + IF + LSTM + neighbour correlation,
                        and for every anomaly, performs inline RCA
                        (RF classification + k-NN similarity search).
                        Emits structured JSON events directly to rca_feed.jsonl.

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
"""

import os, sys, json, time, logging, argparse, warnings
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque, OrderedDict
from copy import deepcopy

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report
from sklearn.neighbors import NearestNeighbors
import joblib

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
os.environ["PYTHONWARNINGS"] = "ignore"

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
IF_PATH     = MODEL_DIR / "isolation_forest.joblib"
SCALER_PATH = MODEL_DIR / "scaler.joblib"
LSTM_PATH   = MODEL_DIR / "lstm_predictor.pt"

# RCA models
RF_PATH          = MODEL_DIR / "rca_rf_classifier.joblib"
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
class LSTMAutoencoder(nn.Module):
    """
    Trained on NORMAL sequences only.
    High reconstruction error at inference -> likely anomaly.
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
        val = row.get(kpi, np.nan)
        if pd.isna(val):
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
      1. StandardScaler + Isolation Forest  (on time_series_kpi.csv)
      2. LSTM predictor                     (on time_series_kpi.csv)
      3. RCA scaler + Random Forest         (on labeled_incidents.csv)
      4. k-NN similarity index              (on labeled_incidents.csv)
    """
    def __init__(self, seq_len: int = 16, sample_frac: float = 0.15):
        self.seq_len     = seq_len
        self.sample_frac = sample_frac
        self.device      = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Anomaly detection models
        self.scaler      = StandardScaler()
        self.lstm_ae     = None
        self.tcnn        = None

        # RCA models
        self.rca_scaler  = StandardScaler()
        self.le          = LabelEncoder()
        self.rf          = RandomForestClassifier(
            n_estimators=300, max_depth=20, min_samples_leaf=2,
            class_weight="balanced", random_state=42, n_jobs=None,
        )
        self.knn         = NearestNeighbors(n_neighbors=5, metric="euclidean", n_jobs=None)
        self.incident_db: list[dict] = []

    # ── Load KPI data ─────────────────────────────────────────────────────────
    def _load_kpi_data(self) -> pd.DataFrame:
        log.info(f"Loading KPI data from {TS_KPI_PATH} ...")
        df = pd.read_csv(TS_KPI_PATH, parse_dates=["timestamp"])
        df = df.dropna(subset=KPI_FEATURES_ANOMALY)
        df = df.sample(frac=self.sample_frac, random_state=42).sort_values("timestamp")
        log.info(f"  Loaded {len(df):,} rows after {self.sample_frac*100:.0f}% sample")
        return df

    # ── Build Sequences ───────────────────────────────────────────────────────
    def _build_sequences(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        X_scaled = self.scaler.transform(df[KPI_FEATURES_ANOMALY].values)
        y_labels = (df["label"] == "anomaly").astype(np.float32).values

        Xs, ys = [], []
        # Create sequences per cell to avoid cross-cell contamination
        for cell_id, group in df.groupby("cell_id"):
            idx = group.index
            group_X = X_scaled[df.index.isin(idx)]
            group_y = y_labels[df.index.isin(idx)]
            for i in range(len(group_X) - self.seq_len):
                Xs.append(group_X[i : i + self.seq_len])
                ys.append(1.0 if group_y[i : i + self.seq_len].sum() > 0 else 0.0)

        return np.array(Xs, dtype=np.float32), np.array(ys, dtype=np.float32)

    # ── Train DL Models ───────────────────────────────────────────────────────
    def _train_dl_models(self, df: pd.DataFrame):
        log.info("Scaling features and building sequences ...")
        self.scaler.fit(df[KPI_FEATURES_ANOMALY].values)
        X_seq, y_seq = self._build_sequences(df)
        
        if len(X_seq) == 0:
            log.error("No sequences built. Check chunk sizes/sample block.")
            return

        split = int(0.85 * len(X_seq))
        X_tr, X_val = X_seq[:split], X_seq[split:]
        y_tr, y_val = y_seq[:split], y_seq[split:]

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

        log.info("Training LSTM-Autoencoder on NORMAL sequences ...")
        self.lstm_ae = LSTMAutoencoder(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        optim_ae = torch.optim.Adam(self.lstm_ae.parameters(), lr=1e-3)
        self.lstm_ae.train()

        for epoch in range(1, 16):
            epoch_loss = 0.0
            for (batch_x,) in normal_loader:
                batch_x = batch_x.to(self.device)
                optim_ae.zero_grad()
                loss = F.mse_loss(self.lstm_ae(batch_x), batch_x)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.lstm_ae.parameters(), 1.0)
                optim_ae.step()
                epoch_loss += loss.item() * len(batch_x)
            
            epoch_loss /= max(len(X_tr_normal), 1)
            if epoch % 5 == 0:
                log.info(f"  LSTM-AE Epoch {epoch:02d} — loss={epoch_loss:.5f}")

        # Calibrate LSTM-AE continuously avoiding OOM
        if len(val_normal) > 0:
            self.lstm_ae.eval()
            mse_list = []
            with torch.no_grad():
                for (batch_x,) in val_loader:
                    batch_x = batch_x.to(self.device)
                    mse = torch.mean((batch_x - self.lstm_ae(batch_x)) ** 2, dim=(1, 2))
                    mse_list.append(mse.cpu())
            mse_tensor = torch.cat(mse_list)
            self.lstm_ae.mse_p5 = torch.quantile(mse_tensor, 0.05).to(self.device)
            self.lstm_ae.mse_p95 = torch.quantile(mse_tensor, 0.95).to(self.device)

        # 2. Train TCNN on all sequences (Supervised)
        log.info("Training Temporal CNN on ALL sequences ...")
        tcnn_loader = DataLoader(
            TensorDataset(torch.FloatTensor(X_tr), torch.FloatTensor(y_tr)), 
            batch_size=batch_size, shuffle=True
        )

        self.tcnn = TemporalCNN(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        optim_cnn = torch.optim.Adam(self.tcnn.parameters(), lr=1e-3, weight_decay=1e-4)

        n_pos = (y_tr == 1).sum().clip(min=1)
        n_neg = (y_tr == 0).sum().clip(min=1)
        pos_w = torch.tensor(n_neg / n_pos).clamp(0.5, 10.0).to(self.device)
        bce = nn.BCELoss(reduction='none')

        self.tcnn.train()
        for epoch in range(1, 16):
            epoch_loss = 0.0
            for batch_x, batch_y in tcnn_loader:
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
                
            epoch_loss /= max(len(X_tr), 1)
            if epoch % 5 == 0:
                log.info(f"  TCNN Epoch {epoch:02d} — weighted bce loss={epoch_loss:.5f}")

        # Save models
        torch.save(self.lstm_ae.state_dict(), MODEL_DIR / "lstm_ae.pt")
        torch.save(self.tcnn.state_dict(), MODEL_DIR / "tcnn.pt")
        joblib.dump(self.scaler, SCALER_PATH)
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

    # ── Train RF classifier ───────────────────────────────────────────────────
    def _train_classifier(self, df: pd.DataFrame):
        log.info("Training RandomForest RCA classifier ...")
        X = self.rca_scaler.fit_transform(df[KPI_FEATURES_RCA].values)
        y = self.le.fit_transform(df["root_cause"].values)

        split = int(0.8 * len(X))
        X_tr, X_val = X[:split], X[split:]
        y_tr, y_val = y[:split], y[split:]

        self.rf.fit(X_tr, y_tr)
        y_pred = self.rf.predict(X_val)

        report = classification_report(
            y_val, y_pred,
            target_names=self.le.classes_,
            zero_division=0,
        )
        log.info("RF classifier evaluation:\n" + report)

        # Feature importance summary
        importances = sorted(
            zip(KPI_FEATURES_RCA, self.rf.feature_importances_),
            key=lambda x: x[1], reverse=True,
        )
        log.info("Top-5 most important KPIs for RCA:")
        for feat, imp in importances[:5]:
            log.info(f"  {feat:<30s} {imp:.4f}")

        joblib.dump(self.rf,     RF_PATH)
        joblib.dump(self.rca_scaler, RCA_SCALER_PATH)
        joblib.dump(self.le,     LABEL_ENC_PATH)
        joblib.dump(KPI_FEATURES_RCA, MODEL_DIR / "rca_kpi_features.joblib")
        log.info(f"  Classifier saved -> {RF_PATH}")

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
        log.info(f"  k-NN index built on {len(self.incident_db):,} incidents -> {KNN_PATH}")

    # ── Run full training ─────────────────────────────────────────────────────
    def run(self):
        log.info("=" * 60)
        log.info("BATCH TRAINING — DetectionAgent")
        log.info("=" * 60)

        # Phase A: Anomaly detection models
        log.info("-" * 60)
        log.info("Phase A: Deep Learning Anomaly Models")
        log.info("-" * 60)
        df_kpi = self._load_kpi_data()
        self._train_dl_models(df_kpi)

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
        required = [RF_PATH, RCA_SCALER_PATH, LABEL_ENC_PATH, KNN_PATH, INCIDENT_DB_PATH]
        if not all(p.exists() for p in required):
            raise FileNotFoundError("RCA models not found. Run with --mode train first.")

        self.rf           = joblib.load(RF_PATH)
        self.rca_scaler   = joblib.load(RCA_SCALER_PATH)
        self.le           = joblib.load(LABEL_ENC_PATH)
        self.knn          = joblib.load(KNN_PATH)
        self.incident_db  = joblib.load(INCIDENT_DB_PATH)

        # Restore the exact feature list used during training
        feat_path = MODEL_DIR / "rca_kpi_features.joblib"
        if feat_path.exists():
            KPI_FEATURES_RCA = joblib.load(feat_path)
            log.info(f"  Restored {len(KPI_FEATURES_RCA)} RCA features from saved model")
        log.info("  RCA models loaded [OK]")

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

    def _classify(self, x_raw: np.ndarray) -> list[dict]:
        x_scaled = self.rca_scaler.transform(x_raw.reshape(1, -1))
        proba    = self.rf.predict_proba(x_scaled)[0]
        classes  = self.le.classes_

        ranked = sorted(
            [{"cause": str(c), "probability": round(float(p), 4)} for c, p in zip(classes, proba)],
            key=lambda d: d["probability"],
            reverse=True,
        )
        return ranked

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

        # 1 — RF ranked causes
        ranked_causes = self._classify(x_raw)
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
      2. Isolation Forest scores
      3. LSTM predicts future anomaly score
      4. Neighbour correlation check
      5. Fuse signals → anomaly decision
      6. If anomaly → inline RCA (RF + k-NN)
      7. Emit combined event to rca_feed.jsonl
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

        self._load_models()

    def _load_models(self):
        log.info("Loading anomaly detection models ...")
        ae_path = MODEL_DIR / "lstm_ae.pt"
        tcnn_path = MODEL_DIR / "tcnn.pt"
        
        if not SCALER_PATH.exists() or not ae_path.exists() or not tcnn_path.exists():
            raise FileNotFoundError("Anomaly models not found. Run with --mode train first.")

        self.scaler = joblib.load(SCALER_PATH)

        self.lstm_ae = LSTMAutoencoder(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        self.lstm_ae.load_state_dict(torch.load(ae_path, map_location=self.device))
        self.lstm_ae.eval()

        self.tcnn = TemporalCNN(input_dim=len(KPI_FEATURES_ANOMALY)).to(self.device)
        self.tcnn.load_state_dict(torch.load(tcnn_path, map_location=self.device))
        self.tcnn.eval()

        log.info("  DL Anomaly models loaded [OK]")

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
                      tcnn_score: float | None, neighbour_escalate: bool = False) -> dict:
        votes = 0
        if rule["rule_triggered"]: votes += 1
        if ae_score is not None and ae_score > 5.0: votes += 1
        if tcnn_score is not None and tcnn_score > 5.0: votes += 1

        combined_score = round(
            (rule["rule_score"] * 0.35) +
            ((ae_score or 0)    * 0.25) +
            ((tcnn_score or 0)  * 0.40), 3
        )

        if votes == 0: final_label = "normal"
        elif votes == 1: final_label = "low"
        elif votes == 2: final_label = "medium"
        else: final_label = "high"

        if final_label == "high" and neighbour_escalate:
            final_label = "critical"

        return {
            "votes":               votes,
            "combined_score":      combined_score,
            "final_label":         final_label,
            "is_anomaly":          final_label != "normal",
            "neighbour_escalated": final_label == "critical",
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
        self.stats["rca_diagnosed"] += 1

    def run(self):
        log.info("=" * 60)
        log.info("LIVE STREAM INFERENCE — DetectionAgent")
        log.info(f"  Feed output -> {RCA_FEED}")
        log.info("=" * 60)

        # Clear previous feed
        RCA_FEED.write_text("")

        with open(RCA_FEED, "a") as feed_file:
            reader = pd.read_csv(
                TS_KPI_PATH,
                parse_dates=["timestamp"],
                chunksize=self.chunk_size,
            )

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
                
                if valid_sequences:
                    batch_tensor = torch.tensor(np.array(valid_sequences), dtype=torch.float32).to(self.device)
                    with torch.no_grad():
                        ae_batch = self.lstm_ae.anomaly_score(batch_tensor) * 10.0
                        tcnn_batch = self.tcnn(batch_tensor).squeeze(-1).cpu().numpy() * 10.0
                        
                    for j, original_idx in enumerate(valid_indices):
                        ae_scores[original_idx] = round(float(ae_batch[j]), 3)
                        tcnn_scores[original_idx] = round(float(tcnn_batch[j]), 3)

                # ── Fusion & Emission Spooling ──
                json_buffer = []

                for i, row in enumerate(records):
                    rule_result = rule_engine(row)
                    ae_score = ae_scores[i]
                    tcnn_score = tcnn_scores[i]

                    pre_anomaly = (
                        rule_result["rule_triggered"] or 
                        (ae_score is not None and ae_score > 5.0) or
                        (tcnn_score is not None and tcnn_score > 5.0)
                    )
                    neighbour_escalate = self._neighbour_vote(
                        str(row["cell_id"]), str(row["timestamp"]), pre_anomaly
                    )

                    fusion = self._fuse_signals(
                        rule_result, ae_score, tcnn_score, neighbour_escalate
                    )

                    if fusion["is_anomaly"]:
                        self.stats["anomalies"] += 1
                    if fusion.get("neighbour_escalated"):
                        self.stats["critical_escalations"] += 1

                    if fusion["is_anomaly"]:
                        def _safe(col, default=""):
                            val = row.get(col, default)
                            return val if pd.notna(val) else default

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
                            "processed_at":      datetime.utcnow().isoformat() + "Z",
                            "source_event_id":   f"EVT-{self.stats['processed']:07d}",
                            "timestamp":         str(row["timestamp"]),
                            "cell_id":           str(row["cell_id"]),
                            "site_id":           _safe("site_id"),
                            "region":            _safe("region"),
                            "vendor":            _safe("vendor"),
                            "nr_band":           _safe("nr_band"),
                            "network_slice":     _safe("network_slice"),
                            "anomaly_severity":  fusion["final_label"],
                            "anomaly_score":     fusion["combined_score"],
                            "kpi_snapshot":      kpi_snapshot,
                            "rule_engine":       rule_result,
                            "dl_anomaly_models": {
                                "lstm_ae_score_0_10": ae_score,
                                "tcnn_prob_0_10":     tcnn_score,
                                "ready":              ae_score is not None,
                            },
                            "fusion":            fusion,
                            "neighbour_escalated": fusion.get("neighbour_escalated", False),
                            "rca":               rca_diagnosis,
                            "ground_truth_label": _safe("label", "unknown"),
                        }

                        # Buffer event into memory, rather than blocking on disk I/O
                        json_buffer.append(json.dumps(event, default=str) + "\n")
                        self._emit_console(event)

                # Spool writes chunklessly at IO bandwidth limit
                if json_buffer:
                    feed_file.writelines(json_buffer)

                    if self.stream_delay > 0:
                        time.sleep(self.stream_delay)

        log.info("-" * 60)
        log.info(f"Stream complete. Stats: {self.stats}")
        log.info(f"Feed written -> {RCA_FEED}  ({self.stats['rca_diagnosed']:,} events)")


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
    p.add_argument("--chunk-size",  type=int,   default=500,
                   help="CSV chunk size for streaming (default 500)")
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
