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
)
from sklearn.preprocessing import StandardScaler, LabelEncoder

import tensorflow as tf
from tensorflow.keras import Sequential, Input
from tensorflow.keras.layers import LSTM, Dense, Dropout, BatchNormalization
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint


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
TARGET = "severity"
SEQUENCE_LENGTH = 10
TEST_RATIO = 0.2
EPOCHS = 40
BATCH_SIZE = 64

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


def load_and_prepare_data() -> tuple[pd.DataFrame, LabelEncoder]:
    df = pd.read_csv(DATA_PATH)
    print("Initial shape:", df.shape)

    required_cols = [
        "rsrp", "sinr", "rsrq", "throughput_dl", "throughput_ul",
        "timestamp", "lat", "lon", TARGET
    ]
    missing_required = [c for c in required_cols if c not in df.columns]
    if missing_required:
        raise ValueError(f"Missing required columns: {missing_required}")

    # Missing values
    df["throughput_ul"] = df["throughput_ul"].fillna(df["throughput_ul"].median())
    df["throughput_dl"] = df["throughput_dl"].fillna(df["throughput_dl"].median())
    df = df.dropna(subset=["lat", "lon"]).copy()

    # Timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Time features
    df["hour"] = df["timestamp"].dt.hour
    df["day"] = df["timestamp"].dt.day
    df["weekday"] = df["timestamp"].dt.weekday

    # Keep numeric clean
    for col in FEATURE_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=FEATURE_COLS + [TARGET]).copy()

    # Encode severity classes
    label_encoder = LabelEncoder()
    df[TARGET] = label_encoder.fit_transform(df[TARGET])

    print("Shape after preprocessing:", df.shape)
    print("\nEncoded classes:")
    for i, label in enumerate(label_encoder.classes_):
        print(f"{i} -> {label}")

    print("\nGlobal class balance:")
    print(pd.Series(df[TARGET]).value_counts().sort_index())
    print()
    print(pd.Series(df[TARGET]).value_counts(normalize=True).sort_index())

    return df, label_encoder


def chronological_split(df: pd.DataFrame, test_ratio: float):
    split_idx = int(len(df) * (1 - test_ratio))
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    print("\nChronological split:")
    print("Train rows:", train_df.shape[0])
    print("Test rows :", test_df.shape[0])

    print("\nTrain class balance:")
    print(train_df[TARGET].value_counts().sort_index())
    print(train_df[TARGET].value_counts(normalize=True).sort_index())

    print("\nTest class balance:")
    print(test_df[TARGET].value_counts().sort_index())
    print(test_df[TARGET].value_counts(normalize=True).sort_index())

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


def build_model(input_shape: tuple[int, int], num_classes: int) -> Sequential:
    model = Sequential([
        Input(shape=input_shape),

        LSTM(128, return_sequences=True),
        BatchNormalization(),
        Dropout(0.3),

        LSTM(64, return_sequences=False),
        BatchNormalization(),
        Dropout(0.3),

        Dense(32, activation="relu"),
        Dropout(0.2),

        Dense(num_classes, activation="softmax")
    ])

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"]
    )

    return model


def main():
    df, label_encoder = load_and_prepare_data()
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
        raise ValueError("Not enough rows to create sequences.")

    num_classes = len(label_encoder.classes_)
    model = build_model(
        input_shape=(X_train_seq.shape[1], X_train_seq.shape[2]),
        num_classes=num_classes
    )

    model.summary()

    callbacks = [
        EarlyStopping(
            monitor="val_loss",
            patience=7,
            restore_best_weights=True
        ),
        ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=3,
            min_lr=1e-6
        ),
        ModelCheckpoint(
            filepath=str(MODEL_DIR / "best_lstm_multiclass.keras"),
            monitor="val_loss",
            save_best_only=True
        )
    ]

    history = model.fit(
        X_train_seq,
        y_train_seq,
        validation_split=0.2,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=callbacks,
        verbose=1
    )

    y_prob = model.predict(X_test_seq, verbose=0)
    y_pred = np.argmax(y_prob, axis=1)

    acc = accuracy_score(y_test_seq, y_pred)
    f1 = f1_score(y_test_seq, y_pred, average="weighted")
    cm = confusion_matrix(y_test_seq, y_pred)
    report = classification_report(
        y_test_seq,
        y_pred,
        target_names=label_encoder.classes_,
        zero_division=0
    )

    print("\n=== LSTM Multiclass Evaluation ===")
    print("Accuracy:", acc)
    print("Weighted F1 score:", f1)
    print("\nClassification report:\n")
    print(report)
    print("\nConfusion matrix:\n")
    print(cm)

    model.save(MODEL_DIR / "lstm_multiclass_final.keras")

    metadata = {
        "feature_cols": FEATURE_COLS,
        "sequence_length": SEQUENCE_LENGTH,
        "target": TARGET,
        "classes": label_encoder.classes_.tolist(),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "epochs": EPOCHS,
        "batch_size": BATCH_SIZE,
    }

    with open(MODEL_DIR / "lstm_multiclass_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    with open(RESULTS_DIR / "lstm_multiclass_metrics.txt", "w", encoding="utf-8") as f:
        f.write(f"Accuracy: {acc}\n")
        f.write(f"Weighted F1 score: {f1}\n\n")
        f.write("Classification report:\n")
        f.write(report)
        f.write("\nConfusion matrix:\n")
        f.write(np.array2string(cm))

    print("\nSaved files:")
    print("-", MODEL_DIR / "best_lstm_multiclass.keras")
    print("-", MODEL_DIR / "lstm_multiclass_final.keras")
    print("-", MODEL_DIR / "lstm_multiclass_metadata.json")
    print("-", RESULTS_DIR / "lstm_multiclass_metrics.txt")


if __name__ == "__main__":
    main()