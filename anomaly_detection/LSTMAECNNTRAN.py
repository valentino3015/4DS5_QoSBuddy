"""
LSTMAECNNTRAN.py — Multi-Modal Anomaly Scorer
Trains directly from the real QoSBuddy dataset using `any_degradation`
and `label_*` columns as ground truth.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from collections import deque
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import pandas as pd
import json
import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# CONSTANTS — label columns present in the real CSV
# ─────────────────────────────────────────────────────────────

LABEL_COLS = [
    'label_call_drop_risk',
    'label_low_throughput',
    'label_handover_risk',
    'label_coverage_hole',
    'label_interference',
    'label_voice_quality_risk',
    'label_prb_congestion',
]

# Maps each label column → knowledge-base key
LABEL_TO_KB = {
    'label_call_drop_risk':      'call_drop',
    'label_low_throughput':      'low_throughput',
    'label_handover_risk':       'handover_failure',
    'label_coverage_hole':       'session_data_drop',
    'label_interference':        'interference',
    'label_voice_quality_risk':  'voice_quality',
    'label_prb_congestion':      'capacity_issue',
}

# ─────────────────────────────────────────────────────────────
# FEATURE NORMALISER
# ─────────────────────────────────────────────────────────────

class FeatureNormaliser:
    """Z-score normaliser — fit once on training data, reused at inference."""

    def __init__(self):
        self.mean: Optional[np.ndarray] = None
        self.std:  Optional[np.ndarray] = None

    def fit(self, sequences: np.ndarray):
        flat = sequences.reshape(-1, sequences.shape[-1])
        self.mean = flat.mean(axis=0)
        self.std  = flat.std(axis=0) + 1e-8

    def transform(self, sequences: np.ndarray) -> np.ndarray:
        if self.mean is None:
            return sequences
        return (sequences - self.mean) / self.std

    def fit_transform(self, sequences: np.ndarray) -> np.ndarray:
        self.fit(sequences)
        return self.transform(sequences)


# ─────────────────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────────────────

class LSTMAutoencoder(nn.Module):
    """
    Trained on NORMAL sequences only.
    High reconstruction error at inference → likely anomaly.
    """

    def __init__(self, input_dim: int, hidden_dim: int = 64,
                 latent_dim: int = 16, num_layers: int = 2):
        super().__init__()
        self.encoder_lstm = nn.LSTM(input_dim, hidden_dim, num_layers,
                                    batch_first=True, dropout=0.2)
        self.encoder_fc   = nn.Linear(hidden_dim, latent_dim)
        self.decoder_fc   = nn.Linear(latent_dim, hidden_dim)
        self.decoder_lstm = nn.LSTM(hidden_dim, hidden_dim, num_layers,
                                    batch_first=True, dropout=0.2)
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
        print(f"   LSTM-AE calibrated  p5={self.mse_p5:.5f}  p95={self.mse_p95:.5f}")


class TemporalCNN(nn.Module):
    """
    Supervised model.
    anomaly_head     → binary anomaly probability
    degradation_head → 7-class multi-label degradation probabilities
    """

    N_DEG = len(LABEL_COLS)   # 7

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
        self.anomaly_head     = nn.Sequential(
            nn.Linear(128, 32), nn.ReLU(), nn.Linear(32, 1))
        self.degradation_head = nn.Linear(128, self.N_DEG)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        x = x.permute(0, 2, 1)
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        x = F.relu(self.bn3(self.conv3(x)))
        x = self.pool(x).squeeze(-1)
        x = self.drop(x)
        return (torch.sigmoid(self.anomaly_head(x)).squeeze(-1),
                torch.sigmoid(self.degradation_head(x)))


# ─────────────────────────────────────────────────────────────
# SEQUENCE BUILDER  — reads real CSV with ground-truth labels
# ─────────────────────────────────────────────────────────────

def build_sequences_from_csv(
        csv_path: str,
        engineer,
        window_size: int,
        step: int,
        seq_len: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    df = pd.read_csv(csv_path)
    return build_sequences_from_df(df, engineer, window_size, step, seq_len)


def build_sequences_from_df(
        df: pd.DataFrame,
        engineer,
        window_size: int,
        step: int,
        seq_len: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns
    -------
    X   : (N, seq_len, n_features)  float32
    y   : (N,)                      float32  0/1   from any_degradation
    yd  : (N, 7)                    float32  from label_* columns
    """
    # Normalise label columns (bool / string / int all accepted)
    df['any_degradation'] = (
        pd.to_numeric(df['any_degradation'], errors='coerce').fillna(0).astype(int))
    for col in LABEL_COLS:
        if col in df.columns:
            df[col] = df[col].map(
                {True: 1, False: 0, 'True': 1, 'False': 0, 1: 1, 0: 0}
            ).fillna(0).astype(int)
        else:
            df[col] = 0

    records = df.to_dict('records')
    buf       = deque(maxlen=window_size)
    feat_buf  = deque(maxlen=seq_len)
    lab_buf   = deque(maxlen=seq_len)
    deg_buf   = deque(maxlen=seq_len)

    sequences, labels, deg_labels = [], [], []

    for i, row in enumerate(records):
        buf.append(row)
        if len(buf) < window_size or (i + 1) % step != 0:
            continue

        window = list(buf)
        win_df = pd.DataFrame(window)

        # Feature vector (sorted keys for deterministic ordering)
        feats    = engineer.transform(window)
        feat_vec = np.array([feats[k] for k in sorted(feats.keys())], dtype=np.float32)
        feat_buf.append(feat_vec)

        # Ground-truth: majority vote (≥30% of rows in window are anomalous)
        win_label = int(win_df['any_degradation'].mean() >= 0.3)
        win_deg   = np.array(
            [int(win_df[c].mean() >= 0.3) for c in LABEL_COLS], dtype=np.float32)
        lab_buf.append(win_label)
        deg_buf.append(win_deg)

        if len(feat_buf) < seq_len:
            continue

        sequences.append(np.array(feat_buf, dtype=np.float32))
        labels.append(float(lab_buf[-1]))
        deg_labels.append(np.array(deg_buf[-1], dtype=np.float32))

    return (np.array(sequences,  dtype=np.float32),
            np.array(labels,     dtype=np.float32),
            np.array(deg_labels, dtype=np.float32))


# ─────────────────────────────────────────────────────────────
# RESULT CONTAINER
# ─────────────────────────────────────────────────────────────

@dataclass
class AnomalyResult:
    final_score: float
    is_anomaly: bool
    severity: str
    degradation_type: Optional[str]
    degradation_probability: float
    model_scores: Dict[str, float]
    degradation_probs: Dict[str, float]
    causes: List[str]
    solutions: List[str]


# ─────────────────────────────────────────────────────────────
# SCORER
# ─────────────────────────────────────────────────────────────

class MultiModalScorer:

    SEVERITY = [(0.95, 'CRITICAL'), (0.85, 'HIGH'), (0.70, 'MEDIUM'), (0.50, 'LOW')]

    def __init__(self, knowledge_file_path: str,
                 input_dim: int = 23,
                 seq_length: int = 5,
                 device: str = 'cpu'):

        self.input_dim  = input_dim
        self.seq_length = seq_length
        self.device     = device
        self.normaliser = FeatureNormaliser()

        with open(knowledge_file_path) as f:
            self.kb = json.load(f)

        self.lstm_ae = LSTMAutoencoder(input_dim).to(device)
        self.tcnn    = TemporalCNN(input_dim).to(device)

        self.w_lstm   = 0.30
        self.w_tcnn   = 0.70
        self._trained = False

    # ── public training entry-point ───────────────────────────

    def train_from_csv(self, csv_path: str, engineer,
                       window_size: int = 10, step: int = 2,
                       epochs: int = 40, lr: float = 1e-3):
        """
        Read the real CSV, build sequences, normalise, train both models.
        Must be called before score().
        """
        print("\n[Training] Building sequences from dataset …")
        X, y, yd = build_sequences_from_csv(
            csv_path, engineer, window_size, step, self.seq_length)
        self._train_from_sequences(X, y, yd, epochs, lr)

    def train_from_df(self, df: pd.DataFrame, engineer,
                      window_size: int = 10, step: int = 2,
                      epochs: int = 40, lr: float = 1e-3):
        """
        Train from an in-memory DataFrame (useful for temporal train/test split).
        Must be called before score().
        """
        print("\n[Training] Building sequences from in-memory dataset …")
        X, y, yd = build_sequences_from_df(
            df, engineer, window_size, step, self.seq_length)
        self._train_from_sequences(X, y, yd, epochs, lr)

    def _train_from_sequences(self, X: np.ndarray, y: np.ndarray, yd: np.ndarray,
                              epochs: int, lr: float):
        if len(X) == 0:
            print("[Training] ⚠️  No sequences generated — check split/window params.")
            return

        n_anom = int(y.sum())
        n_norm = len(y) - n_anom
        print(f"[Training] {len(X)} sequences  |  "
              f"{n_anom} anomalies ({n_anom/len(y)*100:.1f}%)  |  {n_norm} normal")

        if n_anom == 0:
            print("[Training] ⚠️  Zero anomaly sequences — check CSV label columns.")
            return

        # Normalise
        X_norm = self.normaliser.fit_transform(X)
        X_t  = torch.FloatTensor(X_norm).to(self.device)
        y_t  = torch.FloatTensor(y).to(self.device)
        yd_t = torch.FloatTensor(yd).to(self.device)

        X_normal = X_t[y_t == 0]

        print(f"\n── LSTM-AE  ({len(X_normal)} normal seqs) ──")
        self._train_lstm(X_normal, epochs, lr)

        print(f"\n── TCNN  ({len(X_t)} seqs, class weight for imbalance) ──")
        self._train_tcnn(X_t, y_t, yd_t, epochs, lr)

        self.lstm_ae.calibrate(X_normal)
        self._trained = True
        print("\n✓ Training complete.\n")

    # ── internal loops ────────────────────────────────────────

    def _train_lstm(self, X_normal: torch.Tensor, epochs: int, lr: float):
        opt   = torch.optim.Adam(self.lstm_ae.parameters(), lr=lr)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
        self.lstm_ae.train()
        for ep in range(epochs):
            opt.zero_grad()
            loss = F.mse_loss(self.lstm_ae(X_normal), X_normal)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.lstm_ae.parameters(), 1.0)
            opt.step(); sched.step()
            if (ep + 1) % 10 == 0:
                print(f"   epoch {ep+1:3d}/{epochs}  loss={loss.item():.6f}")

    def _train_tcnn(self, X: torch.Tensor, y: torch.Tensor,
                    yd: torch.Tensor, epochs: int, lr: float):
        opt   = torch.optim.Adam(self.tcnn.parameters(), lr=lr, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)

        n_pos = (y == 1).sum().clamp(min=1)
        n_neg = (y == 0).sum().clamp(min=1)
        pos_w = (n_neg / n_pos).clamp(0.5, 10.0)

        bce = nn.BCELoss(reduction='none')
        self.tcnn.train()

        for ep in range(epochs):
            opt.zero_grad()
            a_scores, d_scores = self.tcnn(X)

            # Class-balanced anomaly loss
            a_raw  = bce(a_scores, y)
            a_w    = torch.where(y == 1, pos_w, torch.ones_like(y))
            a_loss = (a_raw * a_w).mean()

            # Multi-label degradation loss (auxiliary)
            d_loss = F.binary_cross_entropy(d_scores, yd)

            loss = a_loss + 0.3 * d_loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.tcnn.parameters(), 1.0)
            opt.step(); sched.step()

            if (ep + 1) % 10 == 0:
                print(f"   epoch {ep+1:3d}/{epochs}  "
                      f"total={loss.item():.5f}  "
                      f"anomaly={a_loss.item():.5f}  "
                      f"deg={d_loss.item():.5f}")

    # ── inference ─────────────────────────────────────────────

    def score(self, x: np.ndarray) -> AnomalyResult:
        """x: (seq_len, F) or (1, seq_len, F) — raw unnormalised features."""
        if x.ndim == 2:
            x = x[np.newaxis]

        x_norm = self.normaliser.transform(x)
        t = torch.FloatTensor(x_norm).to(self.device)

        lstm_s = float(self.lstm_ae.anomaly_score(t)[0])

        self.tcnn.eval()
        with torch.no_grad():
            tcnn_s_t, deg_t = self.tcnn(t)
            tcnn_s  = float(tcnn_s_t[0])
            deg_arr = deg_t[0].cpu().numpy()

        deg_probs = {LABEL_TO_KB[lc]: float(np.clip(deg_arr[i], 0, 1))
                     for i, lc in enumerate(LABEL_COLS)}

        final = float(np.clip(self.w_lstm * lstm_s + self.w_tcnn * tcnn_s, 0, 1))

        severity = 'LOW'
        for thresh, sev in self.SEVERITY:
            if final >= thresh:
                severity = sev
                break

        top_deg  = max(deg_probs, key=deg_probs.get)
        top_prob = deg_probs[top_deg]
        kb_entry = self.kb.get(top_deg, {})

        return AnomalyResult(
            final_score=round(final, 4),
            is_anomaly=final > 0.5,
            severity=severity,
            degradation_type=top_deg,
            degradation_probability=round(top_prob, 4),
            model_scores={'lstm': round(lstm_s, 4), 'tcnn': round(tcnn_s, 4)},
            degradation_probs=deg_probs,
            causes=kb_entry.get('causes',    ['Unknown cause'])[:3],
            solutions=kb_entry.get('solutions', ['Check system logs'])[:3],
        )