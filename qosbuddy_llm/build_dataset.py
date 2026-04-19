"""Builds a supervised fine-tuning dataset for QoSBuddy-LLM from project data."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VENDOR_DIR = ROOT / ".vendor"
if VENDOR_DIR.exists() and str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from qosbuddy_llm.prompting import SYSTEM_PROMPT, build_user_prompt, normalize_priority
from qosbuddy_llm.remediation_kb import DEFAULT_REMEDIATION, REMEDIATION_KB

DATA_DIR = ROOT / "data"
LLM_DATA_DIR = DATA_DIR / "llm"
INCIDENTS_PATH = DATA_DIR / "labeled_incidents.csv"
MAPPING_PATH = DATA_DIR / "rca_mapping.json"

KPI_COLUMNS = [
    "RSRP_dBm",
    "SINR_dB",
    "PRB_util_DL_pct",
    "CQI",
    "BLER_DL_pct",
    "throughput_DL_Mbps",
    "latency_ms",
    "call_drop_rate_pct",
    "HO_success_rate_pct",
    "MOS",
    "MIMO_rank",
]


def load_mapping() -> dict:
    if not MAPPING_PATH.exists():
        return {}
    with open(MAPPING_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle).get("CAUSE_TO_SOLUTION", {})


def build_payload(row: pd.Series, kb_entry: dict) -> dict:
    import pandas as pd

    kpi_snapshot = {}
    for column in KPI_COLUMNS:
        value = row.get(column)
        if pd.notna(value):
            kpi_snapshot[column] = round(float(value), 3)

    return {
        "cell_id": str(row.get("cell_id", "")),
        "site_id": str(row.get("site_id", "")),
        "region": str(row.get("region", "")),
        "vendor": str(row.get("vendor", "")),
        "nr_band": str(row.get("nr_band", "")),
        "network_slice": str(row.get("network_slice", "")),
        "severity": str(row.get("severity", "Medium")).lower(),
        "anomaly_score": None,
        "primary_cause": str(row.get("root_cause", "")),
        "rca_confidence_pct": 95.0,
        "neighbour_escalated": str(row.get("severity", "")).strip().lower() == "critical",
        "is_cluster_event": False,
        "kpi_snapshot": kpi_snapshot,
        "rule_breaches": [],
        "similar_incidents": [],
        "fallback_action": kb_entry.get("action", ""),
        "fallback_steps": kb_entry.get("steps", []),
        "fallback_priority": kb_entry.get("priority", "Medium"),
    }


def build_target(row: pd.Series, kb_entry: dict, mapping: dict) -> dict:
    cause = str(row.get("root_cause", ""))
    recommended_solution = str(row.get("recommended_solution", "")).strip()
    kb_action = kb_entry.get("action") or recommended_solution or mapping.get(cause, DEFAULT_REMEDIATION["action"])
    steps = list(kb_entry.get("steps", DEFAULT_REMEDIATION["steps"]))[:5]
    severity = str(row.get("severity", "Medium"))
    explanation = (
        f"The cell shows a {severity.lower()} QoS degradation linked to {cause.lower()}. "
        f"Use the KPI snapshot to confirm the issue and execute the remediation in priority order."
    )
    return {
        "explanation": explanation,
        "priority": normalize_priority(kb_entry.get("priority", severity)),
        "recommended_action": kb_action,
        "steps": steps,
    }


def build_examples() -> list[dict]:
    import pandas as pd

    mapping = load_mapping()
    df = pd.read_csv(INCIDENTS_PATH)
    df = df.dropna(subset=["root_cause", "severity"])
    examples = []
    for _, row in df.iterrows():
        cause = str(row.get("root_cause", ""))
        kb_entry = REMEDIATION_KB.get(cause, DEFAULT_REMEDIATION)
        payload = build_payload(row, kb_entry)
        target = build_target(row, kb_entry, mapping)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(payload)},
            {"role": "assistant", "content": json.dumps(target, ensure_ascii=True)},
        ]
        examples.append(
            {
                "messages": messages,
                "metadata": {
                    "incident_id": str(row.get("incident_id", "")),
                    "root_cause": cause,
                    "severity": str(row.get("severity", "")),
                },
            }
        )
    return examples


def write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Build QoSBuddy-LLM training dataset")
    parser.add_argument("--train-output", default=str(LLM_DATA_DIR / "qosbuddy_llm_train.jsonl"))
    parser.add_argument("--val-output", default=str(LLM_DATA_DIR / "qosbuddy_llm_val.jsonl"))
    parser.add_argument("--val-frac", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    examples = build_examples()
    rng = random.Random(args.seed)
    rng.shuffle(examples)

    split_idx = max(1, int(len(examples) * (1.0 - args.val_frac)))
    train_rows = examples[:split_idx]
    val_rows = examples[split_idx:]

    train_output = Path(args.train_output)
    val_output = Path(args.val_output)
    write_jsonl(train_output, train_rows)
    write_jsonl(val_output, val_rows)

    print(f"Built {len(examples):,} examples")
    print(f"Train: {train_output} ({len(train_rows):,} rows)")
    print(f"Val  : {val_output} ({len(val_rows):,} rows)")


if __name__ == "__main__":
    main()
