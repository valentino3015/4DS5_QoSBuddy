import json
from pathlib import Path
from collections import Counter
from datetime import datetime, UTC

ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = ROOT / "data" / "output" / "remediation_feed.jsonl"
OUT_DIR = ROOT / "data" / "finetune"
OUT_FILE = OUT_DIR / "qosbuddy_sft.jsonl"

WINDOW_SIZES = [5, 10, 20]


def load_events(path: Path):
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def summarize_window(events):
    severity_counter = Counter()
    cause_counter = Counter()
    cell_counter = Counter()
    region_counter = Counter()

    simplified = []

    for ev in events:
        severity = (ev.get("anomaly_severity") or "unknown").lower()
        cell_id = ev.get("cell_id", "unknown")
        region = ev.get("region", "unknown")

        remediation = ev.get("remediation", {})
        cause = remediation.get("cause", "unknown")
        primary_action = remediation.get("primary_action", {})

        severity_counter[severity] += 1
        cause_counter[cause] += 1
        cell_counter[cell_id] += 1
        region_counter[region] += 1

        simplified.append({
            "timestamp": ev.get("timestamp", ""),
            "cell_id": cell_id,
            "region": region,
            "severity": severity,
            "cause": cause,
            "recommended_action": primary_action.get("action", "unknown"),
            "priority": primary_action.get("priority", "unknown"),
            "impact": primary_action.get("impact", "unknown"),
            "anomaly_score": ev.get("anomaly_score", None),
        })

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "events_analyzed": len(events),
        "severity_counts": dict(severity_counter),
        "top_causes": cause_counter.most_common(5),
        "top_cells": cell_counter.most_common(5),
        "top_regions": region_counter.most_common(5),
        "events": simplified,
    }


def build_target_report(summary):
    top_causes = [c[0] for c in summary["top_causes"]]
    top_cells = [c[0] for c in summary["top_cells"]]
    sev = summary["severity_counts"]

    exec_lines = []
    exec_lines.append(
        f"A total of {summary['events_analyzed']} QoS incidents were analyzed."
    )
    if top_causes:
        exec_lines.append(
            f"The dominant issues were {', '.join(top_causes[:2])}."
        )
    if top_cells:
        exec_lines.append(
            f"The most affected cells included {', '.join(top_cells[:3])}."
        )

    incident_lines = []
    incident_lines.append(f"Severity distribution: {sev}.")
    incident_lines.append(f"Top affected regions: {summary['top_regions']}.")

    root_cause_lines = [
        f"- {cause}: {count} occurrence(s)"
        for cause, count in summary["top_causes"]
    ]

    action_lines = []
    seen_actions = set()
    for ev in summary["events"]:
        action = ev["recommended_action"]
        if action not in seen_actions:
            seen_actions.add(action)
            action_lines.append(f"- {action}")

    business_lines = [
        "These incidents may degrade user experience, service continuity, or network efficiency.",
        "Repeated recurring causes should be prioritized for operational review."
    ]

    next_steps = [
        "1. Prioritize repeated root causes on the most impacted cells.",
        "2. Validate execution of the top recommended actions.",
        "3. Monitor the same cells in the next observation window.",
        "4. Escalate persistent incidents for deeper engineering analysis."
    ]

    report = f"""## Executive Summary
{' '.join(exec_lines)}

## Incident Overview
{' '.join(incident_lines)}

## Top Root Causes
{chr(10).join(root_cause_lines) if root_cause_lines else "- None"}

## Recommended Actions
{chr(10).join(action_lines) if action_lines else "- Manual investigation required"}

## Business Impact
{chr(10).join(f"- {x}" for x in business_lines)}

## Next Steps
{chr(10).join(next_steps)}
"""
    return report.strip()


def build_examples(events):
    examples = []
    for window in WINDOW_SIZES:
        if len(events) < window:
            continue
        for end_idx in range(window, len(events) + 1):
            window_events = events[end_idx - window:end_idx]
            summary = summarize_window(window_events)

            example = {
                "instruction": (
                    "Generate a professional telecom QoS incident report from the "
                    "following enriched remediation events. Do not invent facts. "
                    "Use exactly these sections: Executive Summary, Incident Overview, "
                    "Top Root Causes, Recommended Actions, Business Impact, Next Steps."
                ),
                "input": json.dumps(summary, ensure_ascii=False),
                "output": build_target_report(summary),
                "metadata": {
                    "window_size": window
                }
            }
            examples.append(example)
    return examples


def save_jsonl(examples, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    events = load_events(INPUT_FILE)
    if not events:
        raise ValueError("No remediation events found.")

    examples = build_examples(events)
    save_jsonl(examples, OUT_FILE)

    print(f"Loaded events: {len(events)}")
    print(f"Generated training examples: {len(examples)}")
    print(f"Saved to: {OUT_FILE}")


if __name__ == "__main__":
    main()