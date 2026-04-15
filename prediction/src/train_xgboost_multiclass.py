from pathlib import Path

import pandas as pd
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, f1_score
from sklearn.preprocessing import LabelEncoder


def load_and_prepare_data() -> tuple[pd.DataFrame, list[str], str, LabelEncoder]:
    data_path = Path("data_treatement/qosbuddy_dataset_final.csv")
    df = pd.read_csv(data_path)

    print("Initial shape:", df.shape)

    # Missing values
    df["throughput_ul"] = df["throughput_ul"].fillna(df["throughput_ul"].median())
    df["throughput_dl"] = df["throughput_dl"].fillna(df["throughput_dl"].median())
    df = df.dropna(subset=["lat", "lon"]).copy()

    # Timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    df = df.sort_values("timestamp").copy()

    # Time features
    df["hour"] = df["timestamp"].dt.hour
    df["day"] = df["timestamp"].dt.day
    df["month"] = df["timestamp"].dt.month
    df["weekday"] = df["timestamp"].dt.weekday

    # Lag features
    lag_cols = ["rsrp", "sinr", "rsrq", "throughput_dl", "throughput_ul"]
    for col in lag_cols:
        for lag in [1, 2, 3]:
            df[f"{col}_lag{lag}"] = df[col].shift(lag)

    target = "severity"

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

    label_encoder = LabelEncoder()
    df_model[target] = label_encoder.fit_transform(df_model[target])

    print("\nEncoded classes:")
    for i, label in enumerate(label_encoder.classes_):
        print(f"{i} -> {label}")

    return df_model, feature_cols, target, label_encoder


def train_xgboost_multiclass(
    df_model: pd.DataFrame,
    feature_cols: list[str],
    target: str,
    label_encoder: LabelEncoder
) -> None:
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

    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="multi:softmax",
        num_class=len(label_encoder.classes_),
        eval_metric="mlogloss",
        random_state=42
    )

    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    print("\n=== Multiclass Evaluation ===")
    print("Accuracy:", accuracy_score(y_test, y_pred))
    print("Weighted F1 score:", f1_score(y_test, y_pred, average="weighted"))
    print("\nClassification report:\n")
    print(classification_report(
        y_test,
        y_pred,
        target_names=label_encoder.classes_
    ))
    print("\nConfusion matrix:\n")
    print(confusion_matrix(y_test, y_pred))

    importance_df = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_
    }).sort_values(by="importance", ascending=False)

    print("\n=== Feature Importances ===")
    print(importance_df)


if __name__ == "__main__":
    df_model, feature_cols, target, label_encoder = load_and_prepare_data()
    train_xgboost_multiclass(df_model, feature_cols, target, label_encoder)