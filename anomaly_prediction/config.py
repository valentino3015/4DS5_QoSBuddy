# anomaly_prediction/config.py

FEATURE_COLS = [
    "rsrp", "sinr", "rsrq",
    "throughput_dl", "throughput_ul",
    "lat", "lon",
]

TARGET_COLS = [
    "label_call_drop_risk",
    "label_low_throughput",
    "label_handover_risk",
    "label_coverage_hole",
    "label_interference",
    "label_voice_quality_risk",
    "label_prb_congestion",
    "any_degradation",
]

TARGET_LABELS = {
    "label_call_drop_risk":     "Call Drop Risk",
    "label_low_throughput":     "Low Throughput",
    "label_handover_risk":      "Handover Risk",
    "label_coverage_hole":      "Coverage Hole",
    "label_interference":       "Interference",
    "label_voice_quality_risk": "Voice Quality Risk",
    "label_prb_congestion":     "PRB Congestion",
    "any_degradation":          "Global Degradation",
}

THRESHOLDS = {
    "rsrp_weak":     -100,
    "sinr_low":         3,
    "rsrq_low":       -12,
    "tput_dl_low":      5,
    "tput_ul_low":      1,
}