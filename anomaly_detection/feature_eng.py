import numpy as np
import pandas as pd


class QoSFeatureEngineer:
    def __init__(self):
        pass

    def _to_df(self, window):
        return pd.DataFrame(window)

    def _stat_features(self, df):
        return {
            "mean_sinr": df["sinr"].mean(),
            "std_sinr": df["sinr"].std(),
            "min_sinr": df["sinr"].min(),
            "mean_rsrp": df["rsrp"].mean(),
            "std_rsrp": df["rsrp"].std(),
            "min_rsrp": df["rsrp"].min(),
            "mean_rsrq": df["rsrq"].mean(),
            "mean_throughput_dl": df["throughput_dl"].mean(),
            "std_throughput_dl": df["throughput_dl"].std(),
            "mean_latency": df["latency_ms"].mean(),
            "max_latency": df["latency_ms"].max(),
            "mean_prb_dl": df["prb_util_dl_pct"].mean(),
            "mean_prb_ul": df["prb_util_ul_pct"].mean(),
            "mean_mos": df["mos"].mean()
        }

    def _trend_features(self, df):
        return {
            "delta_sinr": df["sinr"].iloc[-1] - df["sinr"].iloc[0],
            "delta_rsrp": df["rsrp"].iloc[-1] - df["rsrp"].iloc[0],
            "delta_throughput": df["throughput_dl"].iloc[-1] - df["throughput_dl"].iloc[0],
        }

    def _interaction_features(self, df):
        sinr = df["sinr"].mean()
        rsrp = df["rsrp"].mean()
        throughput = df["throughput_dl"].mean()
        return {
            "sinr_rsrp_product": sinr * rsrp,
            "throughput_per_sinr": throughput / (abs(sinr) + 1e-5),
            "rsrp_minus_sinr": rsrp - sinr
        }

    def transform(self, window):
        df = self._to_df(window)
        features = {}
        features.update(self._stat_features(df))
        features.update(self._trend_features(df))
        features.update(self._interaction_features(df))
        features["low_sinr_flag"] = 1 if features["mean_sinr"] < 0 else 0
        features["low_rsrp_flag"] = 1 if features["mean_rsrp"] < -100 else 0
        features["high_congestion_flag"] = 1 if features["mean_prb_dl"] > 80 else 0
        return features