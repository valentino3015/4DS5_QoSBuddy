from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split


def load_and_prepare_data() -> tuple[pd.DataFrame, list[str], str]:
    data_path = Path("data_treatement/qosbuddy_dataset_final.csv")
    df = pd.read_csv(data_path)

    print("Initial shape:", df.shape)

    df["throughput_ul_missing"] = df["throughput_ul"].isna().astype(int)
    df["throughput_dl_missing"] = df["throughput_dl"].isna().astype(int)

    df["throughput_ul"] = df["throughput_ul"].fillna(df["throughput_ul"].median())
    df["throughput_dl"] = df["throughput_dl"].fillna(df["throughput_dl"].median())

    df = df.dropna(subset=["lat", "lon"]).copy()

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    df = df.sort_values("timestamp").copy()

    df["hour"] = df["timestamp"].dt.hour
    df["day"] = df["timestamp"].dt.day
    df["month"] = df["timestamp"].dt.month
    df["weekday"] = df["timestamp"].dt.weekday

    lag_cols = ["rsrp", "sinr", "rsrq", "throughput_dl", "throughput_ul"]

    for col in lag_cols:
        for lag in [1, 2, 3]:
            df[f"{col}_lag{lag}"] = df[col].shift(lag)

    target = "any_degradation"

    feature_cols = [
        "rsrp_lag1", "rsrp_lag2", "rsrp_lag3",
        "sinr_lag1", "sinr_lag2", "sinr_lag3",
        "rsrq_lag1", "rsrq_lag2", "rsrq_lag3",
        "throughput_dl_lag1", "throughput_dl_lag2", "throughput_dl_lag3",
        "throughput_ul_lag1", "throughput_ul_lag2", "throughput_ul_lag3",
        "lat", "lon", "hour", "day", "month", "weekday"
    ]

    df_model = df[feature_cols + [target]].dropna().copy()

    print("Model shape:", df_model.shape)
    print("\nClass balance:")
    print(df_model[target].value_counts())
    print()
    print(df_model[target].value_counts(normalize=True))

    return df_model, feature_cols, target


def train_random_forest(df_model: pd.DataFrame, feature_cols: list[str], target: str) -> None:
    X = df_model[feature_cols]
    y = df_model[target]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )

    print("\nTrain/Test shapes:")
    print(X_train.shape, X_test.shape)

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced"
    )

    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    print("\n=== Evaluation ===")
    print("Accuracy:", accuracy_score(y_test, y_pred))
    print("F1 score:", f1_score(y_test, y_pred, average="weighted"))
    print("\nClassification report:\n")
    print(classification_report(y_test, y_pred))
    print("\nConfusion matrix:\n")
    print(confusion_matrix(y_test, y_pred))

    importance_df = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_
    }).sort_values(by="importance", ascending=False)

    print("\n=== Feature Importances ===")
    print(importance_df)


if __name__ == "__main__":
    df_model, feature_cols, target = load_and_prepare_data()
    train_random_forest(df_model, feature_cols, target)