import json
from pathlib import Path

# 👉 Copy your REMEDIATION_KB here (or import it if you prefer)
#from remediation_agent import REMEDIATION_KB, DEFAULT_REMEDIATION
REMEDIATION_KB = {
    "Poor RSRP coverage": {
        "action": "Adjust antenna tilt and increase cell power",
        "steps": [
            "Identify sectors with RSRP below -110 dBm using OMC counters",
            "Reduce mechanical downtilt by 2-3 degrees to extend coverage radius",
            "Increase DL transmission power by 3 dB (verify EIRP regulatory limits first)",
            "Add missing neighbor relations to adjacent cells via ANR",
            "Schedule a drive test to validate the coverage improvement",
        ],
        "priority": "High", "effort": "Medium", "eta_hours": 4, "auto": False,
        "impact": "Resolves coverage hole and reduces call drop rate significantly",
    },
    "High interference (SINR<0)": {
        "action": "Run interference audit and optimize power control",
        "steps": [
            "Pull the inter-cell interference matrix from the OMC dashboard",
            "Identify top-3 interfering cells by PCI and SINR heatmap",
            "Reduce aggressor cell Tx power by 2 dB to lower interference floor",
            "Adjust ICIC parameters to coordinate resource usage across cells",
            "Enable UL closed-loop power control with tighter alpha value",
        ],
        "priority": "Critical", "effort": "Medium", "eta_hours": 2, "auto": True,
        "impact": "Improves SINR by 3-6 dB and boosts user throughput by 20-40%",
    },
    "HO failure": {
        "action": "Tune handover parameters and clean the neighbor list",
        "steps": [
            "Export neighbor relation table and flag missing or stale entries",
            "Reduce the A3 offset from its current value by 2 dB",
            "Shorten Time-to-Trigger (TTT) from 320 ms to 160 ms",
            "Verify X2/Xn interface links are up with all nearby gNBs",
            "Monitor HO success rate for 1 hour after applying changes",
        ],
        "priority": "High", "effort": "Low", "eta_hours": 1, "auto": True,
        "impact": "Restores HO success rate above 95% and eliminates cell-edge call drops",
    },
    "PRB saturation": {
        "action": "Activate carrier aggregation and load balancing",
        "steps": [
            "Enable Carrier Aggregation to add a secondary carrier on the overloaded cell",
            "Enable MLB to offload UEs to adjacent lightly-loaded cells",
            "Lower PRB utilization alarm threshold so MLB triggers earlier",
            "Check scheduler config for fair resource sharing across slices",
            "Flag for Massive MIMO upgrade if PRB stays above 90% for 2+ hours",
        ],
        "priority": "High", "effort": "Low", "eta_hours": 1, "auto": True,
        "impact": "Reduces PRB load by 25-35% and restores average user throughput",
    },
    "Transport congestion": {
        "action": "Reroute traffic and upgrade backhaul QoS settings",
        "steps": [
            "Check transport link utilization on the affected gNB backhaul port",
            "Reroute to alternate path via BGP/OSPF metric adjustment",
            "Apply DSCP remarking to prioritize 5G user-plane (GTP-U) traffic",
            "Tune AQM settings (CoDel or FQ-CoDel) to reduce buffer bloat",
            "Escalate to transport team for capacity upgrade if link stays above 80%",
        ],
        "priority": "Critical", "effort": "High", "eta_hours": 6, "auto": False,
        "impact": "Reduces latency from over 100 ms to under 30 ms, stops RLC retransmissions",
    },
    "Missing neighbor relation": {
        "action": "Run ANR audit and add missing neighbor cells",
        "steps": [
            "Trigger ANR scan on the affected cell",
            "Cross-check with cell topology map for geographically adjacent gNBs",
            "Manually add missing NCRs in the OMC interface",
            "Verify X2/Xn signaling is established with each new neighbor",
            "Run a test handover call to confirm the relationship works",
        ],
        "priority": "Medium", "effort": "Low", "eta_hours": 1, "auto": True,
        "impact": "Eliminates ping-pong HO failures and reduces call drops by 30-50%",
    },
    "Coverage hole": {
        "action": "Deploy a small cell or repeater in the coverage gap",
        "steps": [
            "Confirm the coverage hole via drive test or UE measurement reports",
            "Identify suitable indoor or outdoor small cell deployment sites",
            "Temporarily adjust adjacent macrocell tilt to partially fill the gap",
            "Submit site acquisition request for permanent small cell installation",
            "Integrate small cell with core network and neighbor list",
        ],
        "priority": "High", "effort": "High", "eta_hours": 72, "auto": False,
        "impact": "Permanently resolves coverage gap, improves indoor RSRP by 15-20 dB",
    },
    "PCI collision": {
        "action": "Reassign PCI to eliminate the collision or confusion",
        "steps": [
            "Extract the current PCI allocation plan from the OMC",
            "Identify conflicting PCIs within 3-cell reuse distance (mod-3 collision)",
            "Assign a new PCI from available pool respecting mod-3 and mod-30 rules",
            "Push PCI change via OMC (no service interruption required)",
            "Verify UE RRC measurement reports no longer show PCI confusion",
        ],
        "priority": "Medium", "effort": "Low", "eta_hours": 1, "auto": True,
        "impact": "Eliminates HO confusion and improves cell selection accuracy",
    },
    "UL/DL interference": {
        "action": "Optimize UL power control and activate interference cancellation",
        "steps": [
            "Set UL SINR target to 5 dB and enable closed-loop power control",
            "Enable IRC (Interference Rejection Combining) on affected cells",
            "Check for rogue UEs transmitting at max power causing UL interference",
            "Coordinate with neighboring operators on shared frequency bands",
            "Apply frequency reuse pattern adjustments if TDD interference is the cause",
        ],
        "priority": "High", "effort": "Medium", "eta_hours": 3, "auto": True,
        "impact": "Improves UL BLER from above 15% to below 5%, boosts MOS by 0.5-1.0",
    },
    "PRB congestion": {
        "action": "Load balance users and activate carrier aggregation",
        "steps": [
            "Identify top PRB-consuming UEs via scheduler statistics",
            "Apply QoS throttling to best-effort traffic on the mMTC slice",
            "Activate 5G CA combining n78 and n28 bands for extra capacity",
            "Enable 256-QAM modulation to improve spectral efficiency per PRB",
            "Schedule capacity planning review if peak load exceeds 85% daily",
        ],
        "priority": "High", "effort": "Low", "eta_hours": 1, "auto": True,
        "impact": "Frees 20-30% PRB and restores average user throughput to normal",
    },
    "Low SINR": {
        "action": "Optimize antenna tilt and update beamforming weights",
        "steps": [
            "Reduce electrical downtilt by 1-2 degrees on the affected sector",
            "Update beamforming codebook weights for target UE cluster locations",
            "Enable 3D beamforming if Massive MIMO hardware is available",
            "Verify antenna cable integrity by checking for high VSWR readings",
            "Confirm no neighboring cell is overshooting into this sector",
        ],
        "priority": "High", "effort": "Medium", "eta_hours": 3, "auto": False,
        "impact": "Improves average SINR by 3-5 dB with throughput gains of 15-25%",
    },
    "Overshooting cell": {
        "action": "Increase downtilt to contain the cell footprint",
        "steps": [
            "Increase mechanical downtilt by 3-5 degrees on the overshooting sector",
            "Reduce DL Tx power by 3 dB to shrink the coverage footprint",
            "Update neighbor lists of cells newly exposed after coverage shrink",
            "Verify HO boundaries are re-established correctly after the change",
            "Run an automated coverage verification scan to confirm the fix",
        ],
        "priority": "Medium", "effort": "Low", "eta_hours": 2, "auto": False,
        "impact": "Eliminates interference to 2-4 adjacent cells and reduces call drop rate",
    },
    "PDU session drop": {
        "action": "Check UPF path health and tune session timer parameters",
        "steps": [
            "Verify UPF instance health and check N3/N9 interface status",
            "Extend PDU session inactivity timer from 30 seconds to 120 seconds",
            "Inspect SMF logs for unexpected AMF-triggered session releases",
            "Verify QoS Flow Binding is correctly configured for the affected slice",
            "Restart UPF session management process if drop rate stays above 5%",
        ],
        "priority": "Critical", "effort": "Medium", "eta_hours": 2, "auto": False,
        "impact": "Eliminates unexpected data session interruptions for affected users",
    },
}

DEFAULT_REMEDIATION = {
    "action": "Manual investigation required",
    "steps": [
        "Collect full OMC performance counters for the affected cell",
        "Review the alarm history for the past 24 hours",
        "Perform a drive test in the affected geographic area",
        "Escalate to the Level-2 RF engineering team with collected data",
    ],
    "priority": "Medium", "effort": "High", "eta_hours": 8, "auto": False,
    "impact": "Requires manual analysis to determine the correct resolution path",
}

PRIORITY_SCORE = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
EFFORT_SCORE   = {"Low": 3, "Medium": 2, "High": 1}

OUTPUT_FILE = "train.jsonl"


def format_example(cause, data):
    """Create one training example"""
    
    action = data.get("action", "")
    steps = data.get("steps", [])
    impact = data.get("impact", "")

    # Keep it clean (LLM-friendly)
    steps_text = "; ".join(steps[:3])  # limit steps

    output = (
        f"Causes: {cause}. "
        f"Solutions: {action}. "
        f"Steps: {steps_text}. "
        f"Impact: {impact}"
    )

    text = f"Input: {cause}\nOutput: {output}"

    return {"text": text}


def generate_variations(cause, data):
    """Generate multiple variations per cause (improves training)"""
    
    variations = []

    # Variation 1 (basic)
    variations.append(format_example(cause, data))

    # Variation 2 (more context)
    variations.append({
        "text": f"Input: Issue detected: {cause}\nOutput: {format_example(cause, data)['text'].split('Output: ')[1]}"
    })

    # Variation 3 (more realistic phrasing)
    variations.append({
        "text": f"Input: {cause} observed on network cell\nOutput: {format_example(cause, data)['text'].split('Output: ')[1]}"
    })

    return variations


def main():
    output_path = Path(OUTPUT_FILE)

    all_examples = []

    for cause, data in REMEDIATION_KB.items():
        examples = generate_variations(cause, data)
        all_examples.extend(examples)

    # Optional: include default case
    all_examples.append(format_example("Unknown anomaly", DEFAULT_REMEDIATION))

    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"✅ Generated {len(all_examples)} training examples in {OUTPUT_FILE}")


if __name__ == "__main__":
    main()