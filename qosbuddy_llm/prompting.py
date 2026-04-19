"""Prompt building and JSON parsing for QoSBuddy-LLM."""

from __future__ import annotations

import json
import re
from typing import Any


SYSTEM_PROMPT = (
    "You are QoSBuddy-LLM, a telecom remediation assistant specialized in 5G QoS incidents. "
    "Given an RCA event and KPI snapshot, produce a concise remediation plan in valid JSON only. "
    'Return the keys "explanation", "priority", "recommended_action", and "steps". '
    '"steps" must be an array of short strings ordered by execution priority.'
)


def normalize_priority(value: Any) -> str:
    priority = str(value or "Medium").strip().lower()
    mapping = {
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }
    return mapping.get(priority, "Medium")


def build_llm_payload(rca_event: dict, remediation: dict | None = None) -> dict:
    remediation = remediation or {}
    primary_action = remediation.get("primary_action", {})
    rca = rca_event.get("rca", {})
    payload = {
        "cell_id": rca_event.get("cell_id", ""),
        "site_id": rca_event.get("site_id", ""),
        "region": rca_event.get("region", ""),
        "vendor": rca_event.get("vendor", ""),
        "nr_band": rca_event.get("nr_band", ""),
        "network_slice": rca_event.get("network_slice", ""),
        "severity": rca_event.get("anomaly_severity", "medium"),
        "anomaly_score": rca_event.get("anomaly_score"),
        "primary_cause": rca.get("primary_cause", remediation.get("cause", "")),
        "rca_confidence_pct": rca.get("confidence_pct", remediation.get("confidence_pct", 0)),
        "neighbour_escalated": remediation.get("neighbour_escalated", False),
        "is_cluster_event": remediation.get("is_cluster_event", False),
        "kpi_snapshot": rca_event.get("kpi_snapshot", {}),
        "rule_breaches": rca_event.get("rule_engine", {}).get("breached_kpis", []),
        "similar_incidents": rca.get("similar_incidents", [])[:3],
        "fallback_action": primary_action.get("action", ""),
        "fallback_steps": primary_action.get("steps", []),
        "fallback_priority": primary_action.get("priority", "Medium"),
    }
    return payload


def build_user_prompt(payload: dict) -> str:
    return (
        "Analyze the following 5G QoS incident and generate a remediation plan.\n"
        "Use the RCA, KPI snapshot, and any similar incidents.\n"
        "Keep the explanation clear and operational.\n"
        "Return JSON only.\n\n"
        f"{json.dumps(payload, ensure_ascii=True, indent=2)}"
    )


def extract_json_block(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return None


def parse_llm_response(text: str) -> dict | None:
    json_block = extract_json_block(text)
    if not json_block:
        return None
    try:
        data = json.loads(json_block)
    except json.JSONDecodeError:
        return None

    explanation = str(data.get("explanation", "")).strip()
    recommended_action = str(data.get("recommended_action", "")).strip()
    steps = data.get("steps", [])
    if not isinstance(steps, list):
        steps = [str(steps)]
    clean_steps = [str(step).strip() for step in steps if str(step).strip()]

    parsed = {
        "explanation": explanation,
        "priority": normalize_priority(data.get("priority")),
        "recommended_action": recommended_action,
        "steps": clean_steps[:6],
    }
    if not parsed["explanation"] or not parsed["recommended_action"] or not parsed["steps"]:
        return None
    return parsed

