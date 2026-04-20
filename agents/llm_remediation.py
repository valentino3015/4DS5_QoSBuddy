import json
import requests
from pathlib import Path

RCA_FEED = Path("data/output/rca_feed.jsonl")


# -----------------------------
# LLM CALL (Ollama Mistral)
# -----------------------------
def ask_mistral(prompt: str):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "mistral",
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 50,
                "temperature": 0.3
            }
        }
    )

    data = response.json()
    return data.get("response", "")


# -----------------------------
# LOAD LAST RCA EVENT
# -----------------------------
def load_latest_rca():
    if not RCA_FEED.exists():
        return None

    with open(RCA_FEED, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        return None

    return json.loads(lines[-1])


# -----------------------------
# BUILD PROMPT (IMPORTANT)
# -----------------------------
# def build_prompt(rca_event):
#     return f"""
# You are a telecom RF optimization expert.

# Analyze this RCA event and return ONLY valid JSON:

# RULES:
# Return ONLY valid JSON.
# Do NOT truncate.
# Do NOT add explanations.
# Make sure JSON is complete and valid.

# FIELDS:
# - action (string)
# - priority (Low/Medium/High/Critical)
# - effort (Low/Medium/High)
# - auto (true/false)
# - eta_hours (number)
# - impact (string)

# EVENT:
# Cause: {rca_event["rca"]["primary_cause"]}
# Severity: {rca_event["anomaly_severity"]}
# Confidence: {rca_event["rca"]["confidence_pct"]}
# Cell: {rca_event["cell_id"]}
# KPIs: {rca_event["kpi_snapshot"]}
# """
def build_prompt(rca_event):
    return f"""
You are a 5G RAN remediation assistant.

Given this RCA event, output ONLY ONE SHORT SENTENCE describing the best corrective action.

Rules:
- Output ONLY the action (no JSON, no explanation, no formatting)
- Maximum 20–25 words
- Be direct and operational (like a network engineer command)
- No extra text

RCA EVENT:
{json.dumps(rca_event, indent=2)}

ANSWER:
"""


# -----------------------------
# MAIN TEST FUNCTION
# -----------------------------
def run_llm_once():
    rca = load_latest_rca()

    if not rca:
        print("No RCA data found")
        return

    prompt = build_prompt(rca)
    response = ask_mistral(prompt)

    print("\n===== RAW LLM RESPONSE =====\n")
    print(response)
    print("RAW LENGTH:", len(response))


if __name__ == "__main__":
    run_llm_once()