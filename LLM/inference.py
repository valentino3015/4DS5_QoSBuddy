import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel

BASE_MODEL = "mistralai/Mistral-7B-Instruct-v0.2"
ADAPTER    = "Valentino3015/qosbuddy-lora"   # your HF repo

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
)


def load_model():
    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(ADAPTER)  # tokenizer is in your adapter repo

    print("Loading base model... (downloads ~4GB in 4-bit on first run, then cached)")
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto"
    )

    print("Applying LoRA adapter...")
    model = PeftModel.from_pretrained(base, ADAPTER)
    model.eval()
    print("Model ready.")
    return tokenizer, model


def predict(tokenizer, model, prompt: str, max_new_tokens: int = 800) -> str:
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            repetition_penalty=1.1,
            pad_token_id=tokenizer.eos_token_id
        )
    generated = out[0][inputs["input_ids"].shape[1]:]
    result = tokenizer.decode(generated, skip_special_tokens=True).strip()
    torch.cuda.empty_cache()
    return result


# ── PROMPT BUILDER ───────────────────────────────────────────────

def derive_mode_and_eta(event):
    rca = event['rca']
    severity = event['anomaly_severity'].lower()
    confidence = rca['confidence_pct']
    primary_cause = rca['primary_cause'].lower()
    tags = [t.lower() for t in rca['rca_tags']]

    manual_causes = [
        'x2/xn failure', 'node failure', 'hardware', 'antenna',
        'duplex mismatch', 'pci collision', 'frequency planning',
        'transport', 'fiber', 'backhaul'
    ]
    needs_manual = (
        any(m in primary_cause for m in manual_causes) or
        'transport' in tags or
        severity == 'high' or
        confidence < 15.0
    )

    mode = 'Manual' if needs_manual else 'Auto'
    if mode == 'Manual':
        eta = {'high': 4, 'medium': 8, 'low': 24}.get(severity, 8)
    else:
        eta = {'high': 1, 'medium': 2, 'low': 4}.get(severity, 2)

    return mode, eta


def build_inference_prompt(event):
    rca = event['rca']
    kpi = event['kpi_snapshot']

    mode, eta = derive_mode_and_eta(event)

    ranked_str = ' | '.join(
        f"{c['cause']} ({c['probability']*100:.1f}%)"
        for c in rca['ranked_causes'][:5]
    )
    kpi_str = '\n'.join(f"  - {k}: {v}" for k, v in kpi.items())
    similar = rca.get('similar_incidents', [])
    similar_str = ', '.join(
        f"{s['incident_id']} ({s['root_cause']})" for s in similar
    ) if similar else 'None'

    return f"""[INST] You are a network QoS expert. Analyze this RCA event and respond in plain text with these sections:

            SUMMARY
            INCIDENT INFO
            RCA TAGS
            KPI SNAPSHOT
            REMEDIATION STEPS
            ALTERNATIVE CAUSES

            Event Data:
            - ID: {event['rca_event_id']}
            - Cell: {event['cell_id']} | Site: {event['site_id']} | Region: {event['region']}
            - Vendor: {event['vendor']} | Band: {event['nr_band']} | Slice: {event['network_slice']}
            - Timestamp: {event['timestamp']}
            - Severity: {event['anomaly_severity'].upper()} (score: {event['anomaly_score']})
            - Primary Cause: {rca['primary_cause']} (confidence: {rca['confidence_pct']}%)
            - RCA Tags: {', '.join(rca['rca_tags'])}
            - Recommended Fix: {rca['recommended_solution']}
            - Similar Incidents: {similar_str}
            - Mode: {mode}
            - ETA: {eta}h

            KPIs:
            {kpi_str}

            Ranked Causes:
            {ranked_str}

            Instructions:
            - INCIDENT INFO must include: Cell, Region, Vendor, Band, Slice, Severity, Score, Confidence, ETA, Mode
            - Mode must be exactly "{mode}" — do not change it
            - ETA must be exactly "{eta}h" — do not change it
            - For REMEDIATION STEPS use numbered steps (Give between 3-6)
            - For ALTERNATIVE CAUSES list each with its confidence percentage, Give a maximum of 3.
            - Do not use JSON or markdown tables [/INST]"""


# ── ENTRY POINT ──────────────────────────────────────────────────

if __name__ == "__main__":
    tokenizer, model = load_model()

    sample_event = {
        "rca_event_id": "RCA-0003366",
        "cell_id": "gNB_046_C3",
        "site_id": "gNB_046",
        "region": "Tunis",
        "vendor": "Huawei",
        "nr_band": "n1",
        "network_slice": "eMBB",
        "timestamp": "2024-01-10 12:00:00",
        "anomaly_severity": "low",
        "anomaly_score": 2.008,
        "kpi_snapshot": {
            "RSRP_dBm": -84.4, "SINR_dB": 12.6, "PRB_util_DL_pct": 51.3,
            "PRB_util_UL_pct": 14.8, "CQI": 10.5, "BLER_DL_pct": 2.8,
            "BLER_UL_pct": 2.23, "throughput_DL_Mbps": 69.81,
            "throughput_UL_Mbps": 7.42, "latency_ms": 8.2,
            "call_drop_rate_pct": 0.53, "HO_success_rate_pct": 96.93,
            "MOS": 4.49, "MIMO_rank": 3.71, "active_users": 66.0
        },
        "rca": {
            "primary_cause": "X2/Xn failure",
            "confidence_pct": 8.2,
            "rca_tags": ["transport", "core"],
            "recommended_solution": "X2/Xn interface reset + transport path check",
            "ranked_causes": [
                {"cause": "X2/Xn failure", "probability": 0.0823},
                {"cause": "PRB utilization >85%", "probability": 0.0671},
                {"cause": "HO failure", "probability": 0.0577},
                {"cause": "Low MIMO rank", "probability": 0.0519},
                {"cause": "Low SINR", "probability": 0.0405}
            ],
            "similar_incidents": [
                {"incident_id": "QOS-00860", "root_cause": "Insufficient bandwidth"}
            ]
        }
    }

    prompt = build_inference_prompt(sample_event)
    response = predict(tokenizer, model, prompt)
    print(response)