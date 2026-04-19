import json
import argparse
from pathlib import Path
from collections import Counter
from datetime import datetime
import requests


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = DATA_DIR / "output"

REMEDIATION_FEED = OUTPUT_DIR / "remediation_feed.jsonl"
REPORT_JSON = OUTPUT_DIR / "report_latest.json"
REPORT_MD = OUTPUT_DIR / "report_latest.md"


def load_events(feed_path: Path, limit: int = 50):
    if not feed_path.exists():
        raise FileNotFoundError(f"Feed not found: {feed_path}")

    events = []
    with open(feed_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return events[-limit:]


def build_summary(events):
    severity_counter = Counter()
    cause_counter = Counter()
    cell_counter = Counter()
    region_counter = Counter()

    simplified_events = []

    for ev in events:
        severity = (ev.get("anomaly_severity") or "unknown").lower()
        cell_id = ev.get("cell_id", "unknown")
        region = ev.get("region", "unknown")

        remediation = ev.get("remediation", {})
        cause = remediation.get("cause", "unknown")

        action = remediation.get("primary_action", {})
        action_name = action.get("action", "unknown")
        priority = action.get("priority", "unknown")
        impact = action.get("impact", "unknown")

        severity_counter[severity] += 1
        cause_counter[cause] += 1
        cell_counter[cell_id] += 1
        region_counter[region] += 1

        simplified_events.append({
            "timestamp": ev.get("timestamp", ""),
            "cell_id": cell_id,
            "region": region,
            "severity": severity,
            "cause": cause,
            "recommended_action": action_name,
            "priority": priority,
            "impact": impact,
            "anomaly_score": ev.get("anomaly_score"),
        })

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "events_analyzed": len(events),
        "severity_counts": dict(severity_counter),
        "top_causes": cause_counter.most_common(5),
        "top_cells": cell_counter.most_common(5),
        "top_regions": region_counter.most_common(5),
        "events": simplified_events,
    }

    return summary


def build_prompt(summary):
    return f"""
You are a telecom QoS reporting assistant.

Your task is to generate a clear professional report based only on the provided incident summary.
Do not invent missing facts.
Do not add fake KPIs.
Be concise, structured, and useful for both technical and business readers.

Return the report in markdown with these sections exactly:
1. Executive Summary
2. Incident Overview
3. Top Root Causes
4. Recommended Actions
5. Business Impact
6. Next Steps

Here is the incident summary in JSON:

{json.dumps(summary, indent=2)}
"""


def call_ollama(model: str, prompt: str, host: str = "http://localhost:11434"):
    url = f"{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(url, json=payload, timeout=180)
    response.raise_for_status()
    data = response.json()
    return data.get("response", "").strip()


def save_outputs(summary, report_text):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    report_json_payload = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source_file": str(REMEDIATION_FEED),
        },
        "summary": summary,
        "report_markdown": report_text,
    }

    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report_json_payload, f, indent=2, ensure_ascii=False)

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(report_text)


def parse_args():
    parser = argparse.ArgumentParser(description="QoSBuddy Reporting Agent")
    parser.add_argument("--model", type=str, default="qwen2.5:7b", help="Ollama model name")
    parser.add_argument("--limit", type=int, default=50, help="Number of latest events to analyze")
    parser.add_argument("--host", type=str, default="http://localhost:11434", help="Ollama host URL")
    return parser.parse_args()


def main():
    args = parse_args()

    print("QoSBuddy ReportingAgent starting...")
    print(f"Reading events from: {REMEDIATION_FEED}")

    events = load_events(REMEDIATION_FEED, limit=args.limit)
    if not events:
        print("No events found in remediation feed.")
        return

    print(f"Loaded {len(events)} events")

    summary = build_summary(events)
    prompt = build_prompt(summary)

    print(f"Calling Ollama model: {args.model}")
    report_text = call_ollama(args.model, prompt, host=args.host)

    save_outputs(summary, report_text)

    print("Report generated successfully:")
    print(f" - {REPORT_JSON}")
    print(f" - {REPORT_MD}")


if __name__ == "__main__":
    main()