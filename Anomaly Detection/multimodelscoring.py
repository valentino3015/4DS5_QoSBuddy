"""
multi_modal_scorer.py
Multi-Modal Anomaly Detection for QoSBuddy
Integrates LSTM Autoencoder, Temporal CNN, and Ensemble Scoring
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import json
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# MODEL ARCHITECTURES
# ============================================

class LSTMAutoencoder(nn.Module):
    """LSTM Autoencoder for reconstruction-based anomaly detection"""
    
    def __init__(self, input_dim: int = 40, hidden_dim: int = 64, 
                 latent_dim: int = 16, num_layers: int = 2):
        super().__init__()
        
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
        self.num_layers = num_layers
        
        # Encoder
        self.encoder_lstm = nn.LSTM(
            input_dim, hidden_dim, num_layers, 
            batch_first=True, dropout=0.2
        )
        self.encoder_fc = nn.Linear(hidden_dim, latent_dim)
        
        # Decoder
        self.decoder_fc = nn.Linear(latent_dim, hidden_dim)
        self.decoder_lstm = nn.LSTM(
            hidden_dim, hidden_dim, num_layers,
            batch_first=True, dropout=0.2
        )
        self.decoder_output = nn.Linear(hidden_dim, input_dim)
        
    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """Encode sequence to latent vector"""
        _, (hidden, _) = self.encoder_lstm(x)
        # Use last layer's hidden state
        latent = self.encoder_fc(hidden[-1])
        return latent
    
    def decode(self, latent: torch.Tensor, seq_len: int) -> torch.Tensor:
        """Decode latent vector to sequence"""
        # Repeat latent for each time step
        latent_seq = latent.unsqueeze(1).repeat(1, seq_len, 1)
        decoded = self.decoder_fc(latent_seq)
        decoded, _ = self.decoder_lstm(decoded)
        return self.decoder_output(decoded)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass"""
        latent = self.encode(x)
        return self.decode(latent, x.shape[1])
    
    def anomaly_score(self, x: torch.Tensor) -> np.ndarray:
        """Compute reconstruction error as anomaly score"""
        self.eval()
        with torch.no_grad():
            reconstructed = self.forward(x)
            mse = torch.mean((x - reconstructed) ** 2, dim=(1, 2))
            return mse.cpu().numpy()


class TemporalCNN(nn.Module):
    """Temporal CNN for pattern detection and degradation classification"""
    
    def __init__(self, input_dim: int = 40, num_degradation_types: int = 8):
        super().__init__()
        
        self.conv1 = nn.Conv1d(input_dim, 64, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm1d(64)
        self.conv2 = nn.Conv1d(64, 128, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm1d(128)
        self.conv3 = nn.Conv1d(128, 256, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm1d(256)
        self.conv4 = nn.Conv1d(256, 128, kernel_size=3, padding=1)
        
        self.global_pool = nn.AdaptiveAvgPool1d(1)
        self.dropout = nn.Dropout(0.3)
        
        # Multi-output: anomaly score + degradation probabilities
        self.anomaly_head = nn.Linear(128, 1)
        self.degradation_head = nn.Linear(128, num_degradation_types)
        
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        x shape: (batch, time, features)
        Returns: (anomaly_score, degradation_probs)
        """
        # Convert to (batch, features, time)
        x = x.permute(0, 2, 1)
        
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        x = F.relu(self.bn3(self.conv3(x)))
        x = F.relu(self.conv4(x))
        
        x = self.global_pool(x).squeeze(-1)
        x = self.dropout(x)
        
        anomaly_score = torch.sigmoid(self.anomaly_head(x))
        degradation_probs = torch.sigmoid(self.degradation_head(x))
        
        return anomaly_score, degradation_probs


class TransformerAnomalyDetector(nn.Module):
    """Transformer for complex pattern detection (optional)"""
    
    def __init__(self, input_dim: int = 40, d_model: int = 64, 
                 n_heads: int = 4, num_layers: int = 2, dropout: float = 0.1):
        super().__init__()
        
        self.input_proj = nn.Linear(input_dim, d_model)
        self.pos_encoding = PositionalEncoding(d_model, dropout)
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model, n_heads, dim_feedforward=256, dropout=dropout
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers)
        
        self.anomaly_head = nn.Sequential(
            nn.Linear(d_model, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 1),
            nn.Sigmoid()
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x shape: (batch, time, features)
        Returns: anomaly_score per sample
        """
        x = self.input_proj(x)  # (batch, time, d_model)
        x = self.pos_encoding(x)
        x = x.permute(1, 0, 2)  # (time, batch, d_model) for transformer
        x = self.transformer(x)
        x = x.permute(1, 0, 2)  # (batch, time, d_model)
        
        # Pool over time dimension
        x = x.mean(dim=1)
        return self.anomaly_head(x)


class PositionalEncoding(nn.Module):
    """Positional encoding for transformer"""
    
    def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 5000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * 
                            (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer('pe', pe)
        
    def forward(self, x):
        x = x + self.pe[:x.size(0), :]
        return self.dropout(x)


# ============================================
# ENSEMBLE SCORER
# ============================================

@dataclass
class AnomalyResult:
    """Structured anomaly detection result"""
    final_score: float
    is_anomaly: bool
    severity: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    degradation_type: Optional[str]
    degradation_probability: float
    model_scores: Dict[str, float]
    degradation_probs: Dict[str, float]
    causes: List[str]
    solutions: List[str]


class MultiModalScorer:
    """
    Multi-Modal Anomaly Detection with Ensemble Scoring
    Integrates with knowledge base for RCA
    """
    
    def __init__(self, knowledge_file_path: str, 
                 input_dim: int = 40,
                 seq_length: int = 20,
                 use_transformer: bool = False,
                 device: str = 'cuda' if torch.cuda.is_available() else 'cpu'):
        
        self.input_dim = input_dim
        self.seq_length = seq_length
        self.device = device
        self.use_transformer = use_transformer
        
        # Load knowledge base
        with open(knowledge_file_path, 'r') as f:
            self.knowledge_base = json.load(f)
        
        # Map degradation types to indices
        self.degradation_types = [
            'call_drop', 'voice_quality', 'low_throughput', 
            'high_latency', 'session_data_drop', 'handover_failure', 
            'capacity_issue', 'interference'
        ]
        self.degradation_to_idx = {dt: i for i, dt in enumerate(self.degradation_types)}
        
        # Initialize models
        self.lstm_ae = LSTMAutoencoder(input_dim=input_dim).to(device)
        self.tcnn = TemporalCNN(input_dim=input_dim, 
                                num_degradation_types=len(self.degradation_types)).to(device)
        
        if use_transformer:
            self.transformer = TransformerAnomalyDetector(input_dim=input_dim).to(device)
        
        # Ensemble weights (can be learned or fixed)
        self.ensemble_weights = {
            'lstm': 0.3,
            'tcnn': 0.5,
            'transformer': 0.2 if use_transformer else 0
        }
        
        # Normalize weights
        total = sum(self.ensemble_weights.values())
        self.ensemble_weights = {k: v/total for k, v in self.ensemble_weights.items()}
        
        # Severity thresholds
        self.severity_thresholds = {
            'LOW': 0.5,
            'MEDIUM': 0.7,
            'HIGH': 0.85,
            'CRITICAL': 0.95
        }
        
        logger.info(f"MultiModalScorer initialized on {device}")
        logger.info(f"Ensemble weights: {self.ensemble_weights}")
        
    def load_pretrained_models(self, checkpoint_path: str):
        """Load pretrained model weights"""
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        self.lstm_ae.load_state_dict(checkpoint['lstm_ae'])
        self.tcnn.load_state_dict(checkpoint['tcnn'])
        if self.use_transformer and 'transformer' in checkpoint:
            self.transformer.load_state_dict(checkpoint['transformer'])
        logger.info(f"Loaded pretrained models from {checkpoint_path}")
    
    def _prepare_tensor(self, window_sequence: np.ndarray) -> torch.Tensor:
        """Convert window sequence to tensor"""
        if len(window_sequence.shape) == 2:
            # Add batch dimension
            window_sequence = window_sequence.reshape(1, -1, self.input_dim)
        
        tensor = torch.FloatTensor(window_sequence).to(self.device)
        
        # Ensure correct shape: (batch, seq_len, features)
        if tensor.shape[-1] != self.input_dim:
            tensor = tensor.permute(0, 2, 1)
        
        return tensor
    
    def _get_degradation_details(self, degradation_type: str, 
                                  probability: float) -> Tuple[List[str], List[str]]:
        """Get causes and solutions from knowledge base"""
        if degradation_type not in self.knowledge_base:
            return ["Unknown cause"], ["Check system logs"]
        
        kb_entry = self.knowledge_base[degradation_type]
        
        # Get causes
        causes = kb_entry.get('causes', [])
        if not causes:
            causes = kb_entry.get('symptoms', [])
        
        # Get solutions
        solutions = kb_entry.get('solutions', [])
        
        return causes, solutions
    
    def _determine_severity(self, score: float, 
                           degradation_probs: Dict[str, float]) -> Tuple[str, Optional[str]]:
        """Determine severity and primary degradation type"""
        
        # Find primary degradation type
        if degradation_probs:
            primary_type = max(degradation_probs, key=degradation_probs.get)
            primary_prob = degradation_probs[primary_type]
            
            # Boost severity based on degradation probability
            adjusted_score = min(1.0, score * (1 + primary_prob) / 2)
        else:
            primary_type = None
            adjusted_score = score
        
        # Map score to severity
        for severity, threshold in sorted(self.severity_thresholds.items(), 
                                          key=lambda x: x[1], reverse=True):
            if adjusted_score >= threshold:
                return severity, primary_type
        
        return 'LOW', primary_type
    
    def score(self, window_sequence: np.ndarray) -> AnomalyResult:
        """
        Main scoring method
        
        Args:
            window_sequence: numpy array of shape (seq_len, input_dim) or (batch, seq_len, input_dim)
        
        Returns:
            AnomalyResult with all scores and RCA information
        """
        
        tensor_input = self._prepare_tensor(window_sequence)
        batch_size = tensor_input.shape[0]
        
        model_scores = {}
        degradation_probs = {}
        
        # 1. LSTM Autoencoder Score
        lstm_scores = self.lstm_ae.anomaly_score(tensor_input)
        model_scores['lstm'] = float(lstm_scores[0])
        
        # 2. Temporal CNN Scores
        self.tcnn.eval()
        with torch.no_grad():
            tcnn_anomaly, tcnn_degradations = self.tcnn(tensor_input)
            model_scores['tcnn'] = float(tcnn_anomaly[0][0])
            
            # Get degradation probabilities
            deg_probs = tcnn_degradations[0].cpu().numpy()
            for i, deg_type in enumerate(self.degradation_types):
                degradation_probs[deg_type] = float(deg_probs[i])
        
        # 3. Transformer Score (if enabled)
        if self.use_transformer:
            self.transformer.eval()
            with torch.no_grad():
                transformer_score = self.transformer(tensor_input)
                model_scores['transformer'] = float(transformer_score[0][0])
        
        # 4. Ensemble final score
        final_score = sum(model_scores[k] * self.ensemble_weights.get(k, 0) 
                         for k in model_scores)
        
        # 5. Determine severity and primary degradation
        severity, primary_degradation = self._determine_severity(final_score, degradation_probs)
        
        # 6. Get causes and solutions from knowledge base
        causes = []
        solutions = []
        primary_prob = 0.0
        
        if primary_degradation:
            primary_prob = degradation_probs.get(primary_degradation, 0)
            causes, solutions = self._get_degradation_details(primary_degradation, primary_prob)
        
        # 7. Decision: anomaly if score > 0.5
        is_anomaly = final_score > 0.5
        
        return AnomalyResult(
            final_score=final_score,
            is_anomaly=is_anomaly,
            severity=severity,
            degradation_type=primary_degradation,
            degradation_probability=primary_prob,
            model_scores=model_scores,
            degradation_probs=degradation_probs,
            causes=causes[:3],  # Top 3 causes
            solutions=solutions[:3]  # Top 3 solutions
        )
    
    def score_batch(self, windows: List[np.ndarray]) -> List[AnomalyResult]:
        """Score multiple windows in batch"""
        return [self.score(w) for w in windows]
    
    def update_ensemble_weights(self, feedback: List[Dict]):
        """
        Update ensemble weights based on feedback (simple reinforcement learning)
        
        feedback: list of dicts with 'correct_degradation_type' and 'model_scores'
        """
        # Simplified: increase weight of model that correctly identified degradation
        correct_predictions = defaultdict(float)
        
        for fb in feedback:
            if 'correct_degradation_type' in fb and 'model_scores' in fb:
                # Find which model had highest correlation with correct label
                # This is a placeholder - implement proper weight update logic
                pass
        
        # Re-normalize weights
        total = sum(self.ensemble_weights.values())
        self.ensemble_weights = {k: v/total for k, v in self.ensemble_weights.items()}
        
        logger.info(f"Updated ensemble weights: {self.ensemble_weights}")


# ============================================
# HELPER FUNCTIONS FOR TRAINING
# ============================================

class QoSDataset(torch.utils.data.Dataset):
    """Dataset for training multi-modal models"""
    
    def __init__(self, windows: np.ndarray, labels: np.ndarray):
        """
        windows: shape (n_samples, seq_len, features)
        labels: shape (n_samples, num_degradation_types) - multi-label
        """
        self.windows = torch.FloatTensor(windows)
        self.labels = torch.FloatTensor(labels)
        
    def __len__(self):
        return len(self.windows)
    
    def __getitem__(self, idx):
        return self.windows[idx], self.labels[idx]


def train_lstm_ae(model: LSTMAutoencoder, train_loader, epochs: int = 50, lr: float = 1e-3):
    """Train LSTM Autoencoder on normal data only"""
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()
    
    model.train()
    for epoch in range(epochs):
        total_loss = 0
        for batch in train_loader:
            x, _ = batch  # Ignore labels for AE
            optimizer.zero_grad()
            reconstructed = model(x)
            loss = criterion(reconstructed, x)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        
        if epoch % 10 == 0:
            logger.info(f"LSTM AE Epoch {epoch}, Loss: {total_loss/len(train_loader):.4f}")


def train_tcnn(model: TemporalCNN, train_loader, val_loader, epochs: int = 100, lr: float = 1e-3):
    """Train Temporal CNN for degradation classification"""
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.BCELoss()  # Binary cross-entropy for multi-label
    
    model.train()
    for epoch in range(epochs):
        total_loss = 0
        for batch in train_loader:
            x, y = batch
            optimizer.zero_grad()
            _, pred = model(x)
            loss = criterion(pred, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        
        if epoch % 10 == 0:
            # Validation
            model.eval()
            val_loss = 0
            with torch.no_grad():
                for batch in val_loader:
                    x, y = batch
                    _, pred = model(x)
                    val_loss += criterion(pred, y).item()
            
            logger.info(f"TCNN Epoch {epoch}, Train Loss: {total_loss/len(train_loader):.4f}, "
                       f"Val Loss: {val_loss/len(val_loader):.4f}")
            model.train()


# ============================================
# USAGE EXAMPLE
# ============================================

if __name__ == "__main__":
    # Initialize scorer with knowledge base
    scorer = MultiModalScorer(
        knowledge_file_path='knowledge_base.json',  # Your knowledge file
        input_dim=40,
        seq_length=20,
        use_transformer=False  # Start without transformer
    )
    
    # Simulate a window of data
    # Shape: (seq_length=20, features=40)
    sample_window = np.random.randn(20, 40)
    
    # Get anomaly score
    result = scorer.score(sample_window)
    
    print("=" * 60)
    print("ANOMALY DETECTION RESULT")
    print("=" * 60)
    print(f"Final Score: {result.final_score:.3f}")
    print(f"Is Anomaly: {result.is_anomaly}")
    print(f"Severity: {result.severity}")
    print(f"Primary Degradation: {result.degradation_type}")
    print(f"Confidence: {result.degradation_probability:.2%}")
    print(f"\nModel Scores:")
    for model, score in result.model_scores.items():
        print(f"  {model}: {score:.3f}")
    print(f"\nTop Causes:")
    for cause in result.causes:
        print(f"  - {cause}")
    print(f"\nRecommended Solutions:")
    for solution in result.solutions:
        print(f"  - {solution}")