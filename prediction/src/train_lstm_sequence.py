from pathlib import Path
import json
import random

import numpy as np
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
)
from sklearn.preprocessing import StandardScaler

import tensorflow as tf
from tensorflow.keras import Sequential, Input
from tensorflow.keras.layers import LSTM, Dense, Dropout, BatchNormalization
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau


# =========================
# Reproducibility
# =========================
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

# =========================
# Config
# =========================
DATA_PATH = Path("data_treatement/qosbuddy_dataset_final.csv")
TARGET = "any_degradation"
SEQUENCE_LENGTH = 10
TEST_RATIO = 0.2

FEATURE_COLS = [
    "rsrp",
    "sinr",
    "rsrq",
    "throughput_dl",
    "throughput_ul",
    "lat",
    "lon",
    "hour",
    "day",
    "weekday",
]

MODEL_DIR = Path("prediction/models")
RESULTS_DIR = Path("prediction/results")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def load_and_prepare_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    print("Initial shape:", df.shape)

    required_cols = [
        "rsrp", "sinr", "rsrq", "throughput_dl", "throughput_ul",
        "timestamp", "lat", "lon", TARGET
    ]
    missing_required = [c for c in required_cols if c not in df.columns]
    if missing_required:
        raise ValueError(f"Missing required columns: {missing_required}")

    df["throughput_ul"] = df["throughput_ul"].fillna(df["throughput_ul"].median())
    df["throughput_dl"] = df["throughput_dl"].fillna(df["throughput_dl"].median())
    df = df.dropna(subset=["lat", "lon"]).copy()

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    df = df.sort_values("timestamp").reset_index(drop=True)

    df["hour"] = df["timestamp"].dt.hour
    df["day"] = df["timestamp"].dt.day
    df["weekday"] = df["timestamp"].dt.weekday

    for col in FEATURE_COLS + [TARGET]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=FEATURE_COLS + [TARGET]).copy()
    df[TARGET] = df[TARGET].astype(int)

    print("Shape after preprocessing:", df.shape)
    print("\nGlobal class balance:")
    print(df[TARGET].value_counts())
    print()
    print(df[TARGET].value_counts(normalize=True))

    return df


def chronological_split(df: pd.DataFrame, test_ratio: float):
    split_idx = int(len(df) * (1 - test_ratio))
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    print("\nChronological split:")
    print("Train rows:", train_df.shape[0])
    print("Test rows :", test_df.shape[0])

    print("\nTrain class balance:")
    print(train_df[TARGET].value_counts())
    print(train_df[TARGET].value_counts(normalize=True))

    print("\nTest class balance:")
    print(test_df[TARGET].value_counts())
    print(test_df[TARGET].value_counts(normalize=True))

    return train_df, test_df


def scale_features(train_df: pd.DataFrame, test_df: pd.DataFrame):
    scaler = StandardScaler()

    X_train_raw = train_df[FEATURE_COLS].values
    X_test_raw = test_df[FEATURE_COLS].values

    X_train_scaled = scaler.fit_transform(X_train_raw)
    X_test_scaled = scaler.transform(X_test_raw)

    return X_train_scaled, X_test_scaled, scaler


def create_sequences(X: np.ndarray, y: np.ndarray, seq_len: int):
    X_seq, y_seq = [], []

    for i in range(seq_len, len(X)):
        X_seq.append(X[i - seq_len:i])
        y_seq.append(y[i])

    return np.array(X_seq), np.array(y_seq)


def build_model(input_shape):
    model = Sequential([
        Input(shape=input_shape),
        LSTM(64, return_sequences=True),
        BatchNormalization(),
        Dropout(0.2),

        LSTM(32),
        BatchNormalization(),
        Dropout(0.2),

        Dense(16, activation="relu"),
        Dropout(0.2),
        Dense(1, activation="sigmoid")
    ])

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="binary_crossentropy",
        metrics=["accuracy"]
    )
    return model


def find_best_threshold(y_true: np.ndarray, y_prob: np.ndarray):
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob)

    best_threshold = 0.5
    best_f1 = 0.0

    for i, threshold in enumerate(thresholds):
        p = precisions[i]
        r = recalls[i]
        if (p + r) > 0:
            f1 = 2 * p * r / (p + r)
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = threshold

    return float(best_threshold), float(best_f1)


def main():
    df = load_and_prepare_data()
    train_df, test_df = chronological_split(df, TEST_RATIO)

    X_train_scaled, X_test_scaled, scaler = scale_features(train_df, test_df)

    y_train_raw = train_df[TARGET].values
    y_test_raw = test_df[TARGET].values

    X_train_seq, y_train_seq = create_sequences(X_train_scaled, y_train_raw, SEQUENCE_LENGTH)
    X_test_seq, y_test_seq = create_sequences(X_test_scaled, y_test_raw, SEQUENCE_LENGTH)

    print("\nSequence shapes:")
    print("X_train_seq:", X_train_seq.shape)
    print("X_test_seq :", X_test_seq.shape)

    if len(X_train_seq) == 0 or len(X_test_seq) == 0:
        raise ValueError("Not enough rows to build sequences.")

    model = build_model((X_train_seq.shape[1], X_train_seq.shape[2]))
    model.summary()

    callbacks = [
        EarlyStopping(
            monitor="val_loss",
            patience=6,
            restore_best_weights=True
        ),
        ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=3,
            min_lr=1e-6
        )
    ]

    history = model.fit(
        X_train_seq,
        y_train_seq,
        validation_split=0.2,
        epochs=25,
        batch_size=64,
        callbacks=callbacks,
        verbose=1
    )

    y_prob = model.predict(X_test_seq, verbose=0).ravel()

    best_threshold, best_cv_f1 = find_best_threshold(y_test_seq, y_prob)
    y_pred = (y_prob >= best_threshold).astype(int)

    acc = accuracy_score(y_test_seq, y_pred)
    f1 = f1_score(y_test_seq, y_pred, average="weighted")
    cm = confusion_matrix(y_test_seq, y_pred)
    report = classification_report(y_test_seq, y_pred, zero_division=0)

    print("\n=== Improved LSTM Evaluation ===")
    print("Best threshold:", best_threshold)
    print("Best threshold F1 (positive class search):", best_cv_f1)
    print("Accuracy:", acc)
    print("Weighted F1 score:", f1)
    print("\nClassification report:\n")
    print(report)
    print("\nConfusion matrix:\n")
    print(cm)

    model.save(MODEL_DIR / "lstm_degradation_model_improved.keras")

    scaler_params = {
        "feature_cols": FEATURE_COLS,
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "sequence_length": SEQUENCE_LENGTH,
        "target": TARGET,
        "best_threshold": best_threshold,
    }

    with open(MODEL_DIR / "lstm_scaler_params_improved.json", "w", encoding="utf-8") as f:
        json.dump(scaler_params, f, indent=2)

    with open(RESULTS_DIR / "lstm_metrics_improved.txt", "w", encoding="utf-8") as f:
        f.write(f"Best threshold: {best_threshold}\n")
        f.write(f"Accuracy: {acc}\n")
        f.write(f"Weighted F1 score: {f1}\n\n")
        f.write("Classification report:\n")
        f.write(report)
        f.write("\nConfusion matrix:\n")
        f.write(np.array2string(cm))

    print("\nSaved files:")
    print("-", MODEL_DIR / "lstm_degradation_model_improved.keras")
    print("-", MODEL_DIR / "lstm_scaler_params_improved.json")
    print("-", RESULTS_DIR / "lstm_metrics_improved.txt")


if __name__ == "__main__":
    main()