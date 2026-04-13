"""
LSTMAECNNTRAN.py — Multi-Modal Anomaly Scorer with Training Support
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import json
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────

class LSTMAutoencoder(nn.Module):
    """Reconstruction-based anomaly detection. High error → likely anomaly."""

    def __init__(self, input_dim: int, hidden_dim: int = 64, latent_dim: int = 16, num_layers: int = 2):
        super().__init__()
        self.encoder_lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=0.2)
        self.encoder_fc   = nn.Linear(hidden_dim, latent_dim)
        self.decoder_fc   = nn.Linear(latent_dim, hidden_dim)
        self.decoder_lstm = nn.LSTM(hidden_dim, hidden_dim, num_layers, batch_first=True, dropout=0.2)
        self.decoder_out  = nn.Linear(hidden_dim, input_dim)

        # Running stats for score normalisation (updated during training)
        self.register_buffer('mse_p5',  torch.tensor(0.0))
        self.register_buffer('mse_p95', torch.tensor(1.0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h, _) = self.encoder_lstm(x)
        latent = self.encoder_fc(h[-1])
        repeated = self.decoder_fc(latent).unsqueeze(1).repeat(1, x.shape[1], 1)
        out, _  = self.decoder_lstm(repeated)
        return self.decoder_out(out)

    def anomaly_score(self, x: torch.Tensor) -> np.ndarray:
        self.eval()
        with torch.no_grad():
            recon = self.forward(x)
            mse   = torch.mean((x - recon) ** 2, dim=(1, 2))
            # Normalise to [0,1] using percentile range from training
            score = (mse - self.mse_p5) / (self.mse_p95 - self.mse_p5 + 1e-8)
            return score.clamp(0, 1).cpu().numpy()

    def calibrate(self, normal_data: torch.Tensor):
        """Set normalisation stats from a normal-only dataset."""
        self.eval()
        with torch.no_grad():
            recon = self.forward(normal_data)
            mse   = torch.mean((normal_data - recon) ** 2, dim=(1, 2))
            self.mse_p5  = torch.quantile(mse, 0.05)
            self.mse_p95 = torch.quantile(mse, 0.95)
        logger.info(f"LSTM-AE calibrated | p5={self.mse_p5:.4f}  p95={self.mse_p95:.4f}")


class TemporalCNN(nn.Module):
    """Pattern classification: anomaly score + degradation type probabilities."""

    DEGRADATION_TYPES = [
        'call_drop', 'voice_quality', 'low_throughput', 'high_latency',
        'session_data_drop', 'handover_failure', 'capacity_issue', 'interference'
    ]

    def __init__(self, input_dim: int):
        super().__init__()
        n = len(self.DEGRADATION_TYPES)

        self.conv1 = nn.Conv1d(input_dim, 64,  3, padding=1)
        self.bn1   = nn.BatchNorm1d(64)
        self.conv2 = nn.Conv1d(64,  128, 3, padding=1)
        self.bn2   = nn.BatchNorm1d(128)
        self.conv3 = nn.Conv1d(128, 128, 3, padding=1)
        self.bn3   = nn.BatchNorm1d(128)
        self.pool  = nn.AdaptiveAvgPool1d(1)
        self.drop  = nn.Dropout(0.3)

        self.anomaly_head     = nn.Sequential(nn.Linear(128, 32), nn.ReLU(), nn.Linear(32, 1))
        self.degradation_head = nn.Linear(128, n)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """x: (B, T, F)  →  anomaly_score (B,), degradation_probs (B, n_types)"""
        x = x.permute(0, 2, 1)                      # (B, F, T)
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        x = F.relu(self.bn3(self.conv3(x)))
        x = self.pool(x).squeeze(-1)                 # (B, 128)
        x = self.drop(x)
        return torch.sigmoid(self.anomaly_head(x)).squeeze(-1), torch.sigmoid(self.degradation_head(x))


# ─────────────────────────────────────────
# RESULT CONTAINER
# ─────────────────────────────────────────

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


# ─────────────────────────────────────────
# SCORER  (training + inference)
# ─────────────────────────────────────────

class MultiModalScorer:

    SEVERITY = [(0.95, 'CRITICAL'), (0.85, 'HIGH'), (0.70, 'MEDIUM'), (0.50, 'LOW')]

    def __init__(self, knowledge_file_path: str, input_dim: int = 23,
                 seq_length: int = 5, use_transformer: bool = False,
                 device: str = 'cpu'):

        self.input_dim   = input_dim
        self.seq_length  = seq_length
        self.device      = device

        with open(knowledge_file_path) as f:
            self.kb = json.load(f)

        self.lstm_ae = LSTMAutoencoder(input_dim).to(device)
        self.tcnn    = TemporalCNN(input_dim).to(device)

        # Weights: start even; adjust after training/calibration
        self.w_lstm = 0.35
        self.w_tcnn = 0.65

        self._trained = False

    # ── training ──────────────────────────────────────────────

    def train_models(self, sequences: np.ndarray, labels: np.ndarray,
                     epochs: int = 30, lr: float = 1e-3, verbose: bool = True):
        """
        sequences : (N, seq_len, features)
        labels    : (N,) binary  0=normal  1=anomaly
        """
        X = torch.FloatTensor(sequences).to(self.device)
        y = torch.FloatTensor(labels).to(self.device)

        normal_mask = (y == 0)
        X_normal    = X[normal_mask]

        if verbose:
            print(f"\n── Training LSTM-AE  ({int(normal_mask.sum())} normal samples) ──")
        self._train_lstm(X_normal, epochs, lr, verbose)

        if verbose:
            print(f"\n── Training TCNN  ({len(X)} total samples) ──")
        self._train_tcnn(X, y, epochs, lr, verbose)

        # Calibrate LSTM score range on normal data
        self.lstm_ae.calibrate(X_normal)

        self._trained = True
        if verbose:
            print("\n✓ Models trained and calibrated.\n")

    def _train_lstm(self, X_normal: torch.Tensor, epochs, lr, verbose):
        opt  = torch.optim.Adam(self.lstm_ae.parameters(), lr=lr)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
        self.lstm_ae.train()
        for ep in range(epochs):
            opt.zero_grad()
            recon = self.lstm_ae(X_normal)
            loss  = F.mse_loss(recon, X_normal)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.lstm_ae.parameters(), 1.0)
            opt.step(); sched.step()
            if verbose and (ep + 1) % 10 == 0:
                print(f"   epoch {ep+1:3d}/{epochs}  loss={loss.item():.5f}")

    def _train_tcnn(self, X: torch.Tensor, y: torch.Tensor, epochs, lr, verbose):
        opt   = torch.optim.Adam(self.tcnn.parameters(), lr=lr, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)

        # Class-balance weight
        pos_w = ((y == 0).sum() / (y == 1).sum()).clamp(0.5, 5.0)
        bce   = nn.BCELoss(reduction='none')

        self.tcnn.train()
        for ep in range(epochs):
            opt.zero_grad()
            scores, _ = self.tcnn(X)
            loss_raw   = bce(scores, y)
            weights    = torch.where(y == 1, pos_w, torch.ones_like(y))
            loss       = (loss_raw * weights).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.tcnn.parameters(), 1.0)
            opt.step(); sched.step()
            if verbose and (ep + 1) % 10 == 0:
                print(f"   epoch {ep+1:3d}/{epochs}  loss={loss.item():.5f}")

    # ── inference ─────────────────────────────────────────────

    def score(self, x: np.ndarray) -> AnomalyResult:
        """x: (1, seq_len, features) or (seq_len, features)"""
        if x.ndim == 2:
            x = x[np.newaxis]
        t = torch.FloatTensor(x).to(self.device)

        lstm_s = float(self.lstm_ae.anomaly_score(t)[0])

        self.tcnn.eval()
        with torch.no_grad():
            tcnn_s, deg_t = self.tcnn(t)
            tcnn_s = float(tcnn_s[0])
            deg_arr = deg_t[0].cpu().numpy()

        deg_probs = {dt: float(np.clip(deg_arr[i], 0, 1))
                     for i, dt in enumerate(TemporalCNN.DEGRADATION_TYPES)}

        final = np.clip(self.w_lstm * lstm_s + self.w_tcnn * tcnn_s, 0, 1)

        severity = 'LOW'
        for thresh, sev in self.SEVERITY:
            if final >= thresh:
                severity = sev
                break

        top_deg   = max(deg_probs, key=deg_probs.get)
        top_prob  = deg_probs[top_deg]
        kb_entry  = self.kb.get(top_deg, {})
        causes    = kb_entry.get('causes',    ['Unknown cause'])[:3]
        solutions = kb_entry.get('solutions', ['Check system logs'])[:3]

        return AnomalyResult(
            final_score=round(final, 4),
            is_anomaly=final > 0.5,
            severity=severity,
            degradation_type=top_deg,
            degradation_probability=round(top_prob, 4),
            model_scores={'lstm': round(lstm_s, 4), 'tcnn': round(tcnn_s, 4)},
            degradation_probs=deg_probs,
            causes=causes,
            solutions=solutions,
        )