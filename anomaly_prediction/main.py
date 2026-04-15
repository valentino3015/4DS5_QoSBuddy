from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
import warnings

import numpy as np
import pandas as pd

from prediction_model import (
    train_random_forest_baseline,
    train_xgboost_baseline,
    evaluate_classifier,
    print_evaluation_results,
    print_feature_importance,
    print_aggregated_feature_importance,
)

warnings.filterwarnings("ignore", category=FutureWarning)

# ============================================================
# CONFIG
# ============================================================

DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "data_treatement"
    / "qosbuddy_dataset_enhanced.csv"
)

WINDOW_SIZE = 10
HORIZON = 1
TEST_RATIO = 0.2
RANDOM_STATE = 42
TARGET_COLUMN = "any_degradation"

CANDIDATE_FEATURES = [
    "rsrp",
    "sinr",
    "rsrq",
    "throughput_dl",
    "throughput_ul",
    "latency_ms",
    "prb_util_dl_pct",
    "prb_util_ul_pct",
    "mimo_rank",
    "bler_dl_pct",
    "mos",
    "lat",
    "lon",
]

LABEL_COLUMNS = [
    "label_call_drop_risk",
    "label_low_throughput",
    "label_handover_risk",
    "label_coverage_hole",
    "label_interference",
    "label_voice_quality_risk",
    "label_prb_congestion",
]


# ============================================================
# HELPERS
# ============================================================

def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def load_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    df = pd.read_csv(path)

    print_header("DATASET LOADED")
    print(f"Path: {path}")
    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp").reset_index(drop=True)

    return df


def ensure_target(df: pd.DataFrame) -> pd.DataFrame:
    if TARGET_COLUMN in df.columns:
        return df

    available_labels = [c for c in LABEL_COLUMNS if c in df.columns]
    if not available_labels:
        raise ValueError(
            f"Target '{TARGET_COLUMN}' not found and no label columns available to derive it."
        )

    df[TARGET_COLUMN] = df[available_labels].fillna(0).astype(int).max(axis=1)
    return df


def choose_features(df: pd.DataFrame) -> List[str]:
    features = [c for c in CANDIDATE_FEATURES if c in df.columns]
    if not features:
        raise ValueError("No valid prediction features found in dataset.")
    return features


def basic_cleaning(df: pd.DataFrame, features: List[str]) -> pd.DataFrame:
    work = df.copy()

    for col in features:
        work[col] = pd.to_numeric(work[col], errors="coerce")

    if TARGET_COLUMN == "severity":
        severity_map = {"OK": 0, "WARNING": 1, "CRITICAL": 2}
        work[TARGET_COLUMN] = work[TARGET_COLUMN].map(severity_map)
    else:
        work[TARGET_COLUMN] = pd.to_numeric(work[TARGET_COLUMN], errors="coerce").fillna(0)
        work[TARGET_COLUMN] = (work[TARGET_COLUMN] > 0).astype(int)

    work = work.dropna(subset=[TARGET_COLUMN]).reset_index(drop=True)
    return work


def create_supervised_windows(
    df: pd.DataFrame,
    features: List[str],
    window_size: int,
    horizon: int,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    values = df[features].to_numpy(dtype=float)
    targets = df[TARGET_COLUMN].to_numpy()

    X, y = [], []
    flattened_feature_names: List[str] = []

    for step in range(window_size):
        for feat in features:
            flattened_feature_names.append(f"{feat}_t-{window_size - step}")

    max_index = len(df) - horizon + 1
    for end_idx in range(window_size, max_index):
        start_idx = end_idx - window_size
        target_idx = end_idx + horizon - 1

        window = values[start_idx:end_idx]
        if len(window) != window_size:
            continue

        X.append(window.flatten())
        y.append(targets[target_idx])

    if not X:
        raise ValueError("No training windows could be created. Check window size and dataset length.")

    return np.array(X), np.array(y), flattened_feature_names


def time_split(
    X: np.ndarray,
    y: np.ndarray,
    test_ratio: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    split_idx = int(len(X) * (1 - test_ratio))
    if split_idx <= 0 or split_idx >= len(X):
        raise ValueError("Invalid train/test split. Adjust TEST_RATIO or dataset size.")

    return X[:split_idx], X[split_idx:], y[:split_idx], y[split_idx:]


def show_dataset_summary(df: pd.DataFrame, features: List[str], y: np.ndarray) -> None:
    print_header("FEATURES USED")
    print(", ".join(features))

    print_header("TARGET DISTRIBUTION")
    unique, counts = np.unique(y, return_counts=True)
    for label, count in zip(unique, counts):
        ratio = count / len(y)
        print(f"Class {label}: {count} samples ({ratio:.2%})")

    missing_ratio = df[features].isna().mean().sort_values(ascending=False)
    print_header("MISSING RATIO BY FEATURE")
    for feat, ratio in missing_ratio.items():
        print(f"{feat:<25} {ratio:.2%}")


# ============================================================
# MAIN PIPELINE
# ============================================================

def main() -> None:
    print_header("QOSBUDDY - ANOMALY PREDICTION PIPELINE")

    df = load_dataset(DATASET_PATH)
    df = ensure_target(df)

    features = choose_features(df)
    df = basic_cleaning(df, features)

    X, y, flattened_feature_names = create_supervised_windows(
        df=df,
        features=features,
        window_size=WINDOW_SIZE,
        horizon=HORIZON,
    )

    show_dataset_summary(df, features, y)

    X_train, X_test, y_train, y_test = time_split(X, y, TEST_RATIO)

    print_header("TRAIN / TEST SPLIT")
    print(f"Train samples: {len(X_train):,}")
    print(f"Test samples : {len(X_test):,}")
    print(f"Window size  : {WINDOW_SIZE}")
    print(f"Horizon      : t+{HORIZON}")

    rf_model = train_random_forest_baseline(
    X_train=X_train,
    y_train=y_train,
    random_state=RANDOM_STATE,
    )

    rf_results = evaluate_classifier(rf_model, X_test, y_test)
    print_evaluation_results(rf_results, model_name="RandomForest Baseline")
    print_feature_importance(rf_model, flattened_feature_names, top_k=15)
    print_aggregated_feature_importance(rf_model, flattened_feature_names)

    xgb_model = train_xgboost_baseline(
        X_train=X_train,
        y_train=y_train,
        random_state=RANDOM_STATE,
    )

    xgb_results = evaluate_classifier(xgb_model, X_test, y_test)
    print_evaluation_results(xgb_results, model_name="XGBoost Baseline")
    print_feature_importance(xgb_model, flattened_feature_names, top_k=15)
    print_aggregated_feature_importance(xgb_model, flattened_feature_names)

    print_header("PIPELINE COMPLETED")
    print("Target predicted: any_degradation")
    print("Models used     : RandomForest baseline + XGBoost baseline")
    print("Next step       : compare the best baseline with an LSTM model")


if __name__ == "__main__":
    main()