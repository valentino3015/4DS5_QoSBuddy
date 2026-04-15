from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
import warnings

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

from prediction_model import (
    train_random_forest_baseline,
    train_xgboost_baseline,
    train_xgboost_multiclass,
    evaluate_classifier,
    evaluate_multiclass_classifier,
    print_evaluation_results,
    print_multiclass_results,
    print_feature_importance,
    print_aggregated_feature_importance,
)

from lstm_model import (
    LSTMTrainingConfig,
    reshape_flat_windows_to_sequences,
    train_lstm_model,
    evaluate_lstm_model,
    print_lstm_results,
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


def build_anomaly_type(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a single multiclass anomaly_type column from existing binary labels
    using business-priority rules.
    """
    work = df.copy()

    priority_rules = [
        ("label_interference", "interference"),
        ("label_low_throughput", "low_throughput"),
        ("label_call_drop_risk", "other_service_issue"),
        ("label_voice_quality_risk", "other_service_issue"),
        ("label_handover_risk", "other_service_issue"),
        ("label_coverage_hole", "other_service_issue"),
        ("label_prb_congestion", "other_service_issue"),
    ]

    anomaly_types = []
    for _, row in work.iterrows():
        assigned = "no_anomaly"
        for label_col, label_name in priority_rules:
            value = row.get(label_col, 0)
            if pd.notna(value) and int(value) == 1:
                assigned = label_name
                break
        anomaly_types.append(assigned)

    work["anomaly_type"] = anomaly_types
    return work


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
    target_col: str,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    values = df[features].to_numpy(dtype=float)
    targets = df[target_col].to_numpy()

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


def show_anomaly_type_distribution(df: pd.DataFrame) -> None:
    print_header("ANOMALY TYPE DISTRIBUTION")
    distribution = df["anomaly_type"].value_counts(dropna=False)
    total = len(df)

    for label, count in distribution.items():
        ratio = count / total
        print(f"{label:<25} {count:>8} ({ratio:.2%})")


def show_real_prediction_example(
    X_test: np.ndarray,
    y_test: np.ndarray,
    features: List[str],
    window_size: int,
    binary_model,
    multiclass_model,
    label_encoder: LabelEncoder,
) -> None:
    print_header("REAL PREDICTION EXAMPLE")

    # predict on all test samples
    y_pred_all = binary_model.predict(X_test)

    # find a true positive: true=1 and pred=1
    matching_indices = np.where((y_test == 1) & (y_pred_all == 1))[0]

    if len(matching_indices) == 0:
        print("No correctly detected positive example found in test set.")
        return

    sample_idx = int(matching_indices[0])
    sample_flat = X_test[sample_idx]
    true_binary = int(y_test[sample_idx])
    binary_pred = int(y_pred_all[sample_idx])

    n_features = len(features)
    sample_seq = sample_flat.reshape(window_size, n_features)
    sample_df = pd.DataFrame(sample_seq, columns=features)

    print(f"Selected test sample index: {sample_idx}")
    print("Example type            : true positive")
    print("\nInput window (10 latest observations):")
    print(sample_df.round(3).to_string(index=False))

    print("\nBinary prediction:")
    print(f"True any_degradation     : {true_binary}")
    print(f"Predicted any_degradation: {binary_pred}")

    multi_pred_encoded = int(multiclass_model.predict(sample_flat.reshape(1, -1))[0])
    multi_pred_label = label_encoder.inverse_transform([multi_pred_encoded])[0]

    print("\nPredicted anomaly type:")
    print(multi_pred_label)


# ============================================================
# MAIN PIPELINE
# ============================================================

def main() -> None:
    print_header("QOSBUDDY - ANOMALY PREDICTION PIPELINE")

    df = load_dataset(DATASET_PATH)
    df = ensure_target(df)
    df = build_anomaly_type(df)

    features = choose_features(df)
    df = basic_cleaning(df, features)

    show_anomaly_type_distribution(df)

    # =========================================================
    # PART 1 - BINARY PREDICTION
    # =========================================================
    X, y, flattened_feature_names = create_supervised_windows(
        df=df,
        features=features,
        window_size=WINDOW_SIZE,
        horizon=HORIZON,
        target_col=TARGET_COLUMN,
    )

    show_dataset_summary(df, features, y)

    X_train, X_test, y_train, y_test = time_split(X, y, TEST_RATIO)

    print_header("TRAIN / TEST SPLIT - BINARY")
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

    n_features = len(features)
    X_train_seq = reshape_flat_windows_to_sequences(X_train, WINDOW_SIZE, n_features)
    X_test_seq = reshape_flat_windows_to_sequences(X_test, WINDOW_SIZE, n_features)

    print_header("LSTM DATA SHAPES")
    print(f"X_train_seq: {X_train_seq.shape}")
    print(f"X_test_seq : {X_test_seq.shape}")

    lstm_config = LSTMTrainingConfig(
        batch_size=128,
        epochs=10,
        learning_rate=1e-3,
        hidden_size=64,
        num_layers=2,
        dropout=0.2,
    )

    lstm_model = train_lstm_model(
        X_train_seq=X_train_seq,
        y_train=y_train,
        config=lstm_config,
    )

    lstm_results = evaluate_lstm_model(
        model=lstm_model,
        X_test_seq=X_test_seq,
        y_test=y_test,
        config=lstm_config,
        threshold=0.5,
    )
    print_lstm_results(lstm_results, model_name="LSTM")

    # =========================================================
    # PART 2 - MULTICLASS ANOMALY TYPE PREDICTION
    # =========================================================
    df_multi = df[df["anomaly_type"] != "no_anomaly"].copy().reset_index(drop=True)

    print_header("MULTICLASS DATASET")
    print(f"Rows without no_anomaly: {len(df_multi):,}")

    label_encoder = LabelEncoder()
    df_multi["anomaly_type_encoded"] = label_encoder.fit_transform(df_multi["anomaly_type"])
    class_names = list(label_encoder.classes_)

    print_header("MULTICLASS CLASSES")
    for idx, name in enumerate(class_names):
        print(f"{idx}: {name}")

    X_multi, y_multi, flattened_feature_names_multi = create_supervised_windows(
        df=df_multi,
        features=features,
        window_size=WINDOW_SIZE,
        horizon=HORIZON,
        target_col="anomaly_type_encoded",
    )

    X_train_multi, X_test_multi, y_train_multi, y_test_multi = time_split(
        X_multi, y_multi, TEST_RATIO
    )

    print_header("TRAIN / TEST SPLIT - MULTICLASS")
    print(f"Train samples: {len(X_train_multi):,}")
    print(f"Test samples : {len(X_test_multi):,}")
    print(f"Window size  : {WINDOW_SIZE}")
    print(f"Horizon      : t+{HORIZON}")
    print(f"Classes      : {len(class_names)}")

    xgb_multi_model = train_xgboost_multiclass(
        X_train=X_train_multi,
        y_train=y_train_multi,
        num_classes=len(class_names),
        random_state=RANDOM_STATE,
    )

    xgb_multi_results = evaluate_multiclass_classifier(
        model=xgb_multi_model,
        X_test=X_test_multi,
        y_test=y_test_multi,
        class_names=class_names,
    )

    print_multiclass_results(
        xgb_multi_results,
        model_name="XGBoost Multiclass Anomaly Type",
    )
    print_feature_importance(xgb_multi_model, flattened_feature_names_multi, top_k=15)
    print_aggregated_feature_importance(xgb_multi_model, flattened_feature_names_multi)

    # =========================================================
    # REAL CASE EXAMPLE
    # =========================================================
    show_real_prediction_example(
    X_test=X_test,
    y_test=y_test,
    features=features,
    window_size=WINDOW_SIZE,
    binary_model=xgb_model,
    multiclass_model=xgb_multi_model,
    label_encoder=label_encoder,
)

    print_header("PIPELINE COMPLETED")
    print("Part 1: Predict future anomaly or not")
    print("Part 2: Predict future anomaly type")
    print("Best binary baseline so far: XGBoost")
    print("Multiclass model added     : XGBoost multiclass")


if __name__ == "__main__":
    main()