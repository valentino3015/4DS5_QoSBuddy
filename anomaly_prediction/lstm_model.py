from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)


class SequenceDataset(Dataset):
    """
    PyTorch dataset for sequence-based anomaly prediction.
    X shape: (n_samples, window_size, n_features)
    y shape: (n_samples,)
    """

    def __init__(self, X: np.ndarray, y: np.ndarray):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.X)

    def __getitem__(self, idx: int):
        return self.X[idx], self.y[idx]


class LSTMPredictor(nn.Module):
    """
    Simple LSTM binary classifier for QoS anomaly prediction.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
    ):
        super().__init__()

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        self.classifier = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        lstm_out, (hidden, _) = self.lstm(x)
        last_hidden = hidden[-1]
        logits = self.classifier(last_hidden).squeeze(1)
        return logits


@dataclass
class LSTMTrainingConfig:
    batch_size: int = 128
    epochs: int = 10
    learning_rate: float = 1e-3
    hidden_size: int = 64
    num_layers: int = 2
    dropout: float = 0.2
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


def reshape_flat_windows_to_sequences(
    X_flat: np.ndarray,
    window_size: int,
    n_features: int,
) -> np.ndarray:
    """
    Convert flattened windows back to 3D sequences for LSTM.
    From (n_samples, window_size * n_features)
    To   (n_samples, window_size, n_features)
    """
    return X_flat.reshape(-1, window_size, n_features)


def build_sequence_dataloaders(
    X_train_seq: np.ndarray,
    y_train: np.ndarray,
    X_test_seq: np.ndarray,
    y_test: np.ndarray,
    batch_size: int = 128,
) -> Tuple[DataLoader, DataLoader]:
    train_dataset = SequenceDataset(X_train_seq, y_train)
    test_dataset = SequenceDataset(X_test_seq, y_test)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    return train_loader, test_loader


def train_lstm_model(
    X_train_seq: np.ndarray,
    y_train: np.ndarray,
    config: LSTMTrainingConfig,
) -> LSTMPredictor:
    """
    Train LSTM binary classifier.
    """
    input_size = X_train_seq.shape[2]
    model = LSTMPredictor(
        input_size=input_size,
        hidden_size=config.hidden_size,
        num_layers=config.num_layers,
        dropout=config.dropout,
    ).to(config.device)

    train_dataset = SequenceDataset(X_train_seq, y_train)
    train_loader = DataLoader(
        train_dataset,
        batch_size=config.batch_size,
        shuffle=True,
    )

    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)

    model.train()
    for epoch in range(config.epochs):
        epoch_loss = 0.0

        for X_batch, y_batch in train_loader:
            X_batch = X_batch.to(config.device)
            y_batch = y_batch.to(config.device)

            optimizer.zero_grad()
            logits = model(X_batch)
            loss = criterion(logits, y_batch)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()

        avg_loss = epoch_loss / max(1, len(train_loader))
        print(f"Epoch {epoch + 1}/{config.epochs} - Loss: {avg_loss:.4f}")

    return model


def evaluate_lstm_model(
    model: LSTMPredictor,
    X_test_seq: np.ndarray,
    y_test: np.ndarray,
    config: LSTMTrainingConfig,
    threshold: float = 0.5,
) -> Dict[str, Any]:
    """
    Evaluate trained LSTM model and return metrics dictionary.
    """
    test_dataset = SequenceDataset(X_test_seq, y_test)
    test_loader = DataLoader(
        test_dataset,
        batch_size=config.batch_size,
        shuffle=False,
    )

    model.eval()
    all_probs = []
    all_preds = []
    all_true = []

    with torch.no_grad():
        for X_batch, y_batch in test_loader:
            X_batch = X_batch.to(config.device)
            logits = model(X_batch)
            probs = torch.sigmoid(logits).cpu().numpy()
            preds = (probs >= threshold).astype(int)

            all_probs.extend(probs.tolist())
            all_preds.extend(preds.tolist())
            all_true.extend(y_batch.numpy().astype(int).tolist())

    results = {
        "accuracy": accuracy_score(all_true, all_preds),
        "precision": precision_score(all_true, all_preds, zero_division=0),
        "recall": recall_score(all_true, all_preds, zero_division=0),
        "f1_score": f1_score(all_true, all_preds, zero_division=0),
        "confusion_matrix": confusion_matrix(all_true, all_preds),
        "classification_report": classification_report(
            all_true, all_preds, zero_division=0
        ),
        "y_pred": np.array(all_preds),
        "y_prob": np.array(all_probs),
    }
    return results


def print_lstm_results(results: Dict[str, Any], model_name: str = "LSTM") -> None:
    print("\n" + "=" * 70)
    print(f"{model_name.upper()} - EVALUATION RESULTS")
    print("=" * 70)
    print(f"Accuracy : {results['accuracy']:.4f}")
    print(f"Precision: {results['precision']:.4f}")
    print(f"Recall   : {results['recall']:.4f}")
    print(f"F1-score : {results['f1_score']:.4f}")

    print("\n" + "=" * 70)
    print("CONFUSION MATRIX")
    print("=" * 70)
    print(results["confusion_matrix"])

    print("\n" + "=" * 70)
    print("CLASSIFICATION REPORT")
    print("=" * 70)
    print(results["classification_report"])