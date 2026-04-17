"""
QoSBuddy -- RemediationAgent (Agent 3)
=======================================
Reads rca_feed.jsonl from Agent 2 (batch catch-up then live tail),
scores remediation actions, and streams everything to a live browser
dashboard over WebSocket + HTTP.

Usage:
    python remediation_agent.py
    python remediation_agent.py --ws-port 9000 --http-port 9001
    python remediation_agent.py --no-browser
    python remediation_agent.py --tail-interval 0.5
    python remediation_agent.py --llm-backend gemini   # requires GEMINI_API_KEY
    python remediation_agent.py --llm-backend ollama   # local Ollama
    python remediation_agent.py --verbose              # detailed terminal trace

Quiet console by default; essentials append to logs/remediation_stream.jsonl.
Full audit: logs/remediation_agent.log
"""

import os, sys, json, time, logging, argparse, threading, asyncio
import webbrowser, http.server, socketserver, warnings, math
import urllib.request, urllib.error
from pathlib import Path
from datetime import datetime
from collections import deque
from copy import deepcopy

warnings.filterwarnings("ignore")

try:
    import websockets
    from websockets.server import serve as ws_serve
except ImportError:
    print("ERROR: websockets not installed. Run: pip install websockets")
    sys.exit(1)

# Paths
ROOT          = Path(__file__).resolve().parent.parent
DATA_DIR      = ROOT / "data"
OUTPUT_DIR    = DATA_DIR / "output"
LOG_DIR       = ROOT / "logs"
DASHBOARD_DIR = ROOT / "dashboard"

for d in [OUTPUT_DIR, LOG_DIR, DASHBOARD_DIR]:
    d.mkdir(parents=True, exist_ok=True)

RCA_FEED         = OUTPUT_DIR / "rca_feed.jsonl"
REMEDIATION_FEED = OUTPUT_DIR / "remediation_feed.jsonl"
TOPOLOGY_PATH    = DATA_DIR / "cell_topology.csv"
STREAM_ESSENTIAL_LOG = LOG_DIR / "remediation_stream.jsonl"

# Logging: quiet console by default; full detail in remediation_agent.log; essentials in remediation_stream.jsonl
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_DETAILED_FMT = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
_CONSOLE_FMT  = logging.Formatter("%(message)s")
log = logging.getLogger("RemediationAgent")
log.handlers.clear()
log.setLevel(logging.DEBUG)
log.propagate = False

_CONSOLE_VERBOSE = False


def _configure_logging(verbose: bool) -> None:
    """Console: warnings only by default; --verbose → INFO on terminal (full audit still in logs/)."""
    global _CONSOLE_VERBOSE
    _CONSOLE_VERBOSE = verbose
    for h in list(log.handlers):
        log.removeHandler(h)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO if verbose else logging.WARNING)
    if verbose:
        sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    else:
        sh.setFormatter(_CONSOLE_FMT)
    fh = logging.FileHandler(LOG_DIR / "remediation_agent.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_DETAILED_FMT)
    log.addHandler(sh)
    log.addHandler(fh)
    for name in ("websockets", "websockets.server", "websockets.client", "websockets.protocol"):
        logging.getLogger(name).setLevel(logging.WARNING)


def clog(msg: str, *args) -> None:
    """Mirror to console when --verbose; always persisted at DEBUG in file."""
    if _CONSOLE_VERBOSE:
        log.info(msg, *args)
    else:
        log.debug(msg, *args)

# Knowledge Base
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


def _build_remediation_prompt(rca_event: dict, remediation: dict) -> str:
    """Shared prompt for Ollama / Gemini — JSON output schema."""
    primary = remediation.get("primary_action", {})
    payload = {
        "cell_id": rca_event.get("cell_id"),
        "severity": rca_event.get("anomaly_severity"),
        "anomaly_score": rca_event.get("anomaly_score"),
        "kpi_snapshot": rca_event.get("kpi_snapshot", {}),
        "rca": rca_event.get("rca", {}),
        "rule_based_recommendation": remediation,
    }
    return (
        "You are a telecom NOC remediation assistant.\n"
        "Refine the rule-based recommendation with concise, safe and actionable guidance.\n"
        "Return ONLY valid JSON with this schema:\n"
        "{\n"
        '  "summary": "short operational summary",\n'
        '  "risk_level": "Low|Medium|High|Critical",\n'
        '  "rollback_steps": ["step1", "step2"],\n'
        '  "operator_notes": ["note1", "note2"],\n'
        '  "revised_primary_action": {\n'
        '    "action": "string",\n'
        '    "steps": ["..."],\n'
        '    "priority": "Low|Medium|High|Critical",\n'
        '    "effort": "Low|Medium|High",\n'
        '    "eta_hours": 1,\n'
        '    "auto": false,\n'
        '    "impact": "string"\n'
        "  }\n"
        "}\n"
        "Rules:\n"
        "- Keep at most 5 action steps.\n"
        "- If severity is critical, force auto=false.\n"
        "- Keep realistic ETA.\n\n"
        f"INPUT_EVENT={json.dumps(payload, ensure_ascii=True)}\n"
        f"CURRENT_PRIMARY_ACTION={json.dumps(primary, ensure_ascii=True)}\n"
    )


def _parse_llm_json_text(text: str) -> dict | None:
    """Strip optional markdown fences and parse JSON."""
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return None


class GeminiRemediationAdvisor:
    """
    Google Gemini (AI Studio / Generative Language API).
    API key: set env GEMINI_API_KEY or GOOGLE_API_KEY — never commit keys.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        timeout_sec: int = 45,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout_sec = timeout_sec
        self._logged_failure = False

    def enrich(self, rca_event: dict, remediation: dict) -> dict | None:
        prompt = _build_remediation_prompt(rca_event, remediation)
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        body = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as e:
            log.debug("Gemini request failed: %s", e)
            if not self._logged_failure:
                log.warning(
                    "Gemini unreachable — using rules-only refinements; "
                    "per-request details in logs/remediation_agent.log (DEBUG). "
                    "Use --verbose for console trace."
                )
                self._logged_failure = True
            return None

        try:
            parts = raw["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            log.debug("Gemini response parse failed (missing candidates/parts)")
            return None

        parsed = _parse_llm_json_text(text)
        if not parsed:
            log.debug("Gemini returned non-JSON text")
        return parsed


class OllamaRemediationAdvisor:
    """
    Optional free local LLM advisor (Ollama backend).
    It enriches recommendations but never blocks the baseline rules pipeline.
    """
    def __init__(self, model: str = "llama3.1:8b", endpoint: str = "http://localhost:11434/api/generate",
                 timeout_sec: int = 25):
        self.model = model
        self.endpoint = endpoint
        self.timeout_sec = timeout_sec
        self._logged_failure = False

    def enrich(self, rca_event: dict, remediation: dict) -> dict | None:
        prompt = _build_remediation_prompt(rca_event, remediation)
        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            answer = (raw.get("response") or "").strip()
            if not answer:
                return None
            parsed = _parse_llm_json_text(answer)
            return parsed
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as e:
            log.debug("Ollama request failed: %s", e)
            if not self._logged_failure:
                log.warning(
                    "Ollama unreachable — using rules-only; see logs/remediation_agent.log. Use --verbose for console."
                )
                self._logged_failure = True
            return None


class RemediationEngine:
    def _score(self, action, confidence):
        p = PRIORITY_SCORE.get(action.get("priority", "Low"), 1)
        e = EFFORT_SCORE.get(action.get("effort", "High"), 1)
        return round(p * e * (confidence / 100.0), 3)

    def _summary(self, cause, action, cell_id, severity, neighbour_escalated=False):
        mode    = "can be applied automatically" if action["auto"] else "requires manual intervention by an RF engineer"
        eta     = str(action["eta_hours"]) + (" hour" if action["eta_hours"] == 1 else " hours")
        cluster = " This is a CLUSTER EVENT — multiple adjacent cells are affected simultaneously."                   if neighbour_escalated else ""
        return (
            f"Cell {cell_id} has a {severity.upper()} severity issue caused by {cause.lower()}.{cluster} "
            f"The recommended fix is to {action['action'].lower()}, which {mode}. "
            f"Expected resolution time is {eta}. "
            f"Once applied, this should {action['impact'].lower()}."
        )

    def recommend(self, rca_event):
        rca                 = rca_event.get("rca", {})
        cause               = rca.get("primary_cause", "")
        confidence          = float(rca.get("confidence_pct", 50.0))
        severity            = rca_event.get("anomaly_severity", "medium")
        cell_id             = rca_event.get("cell_id", "unknown")
        ranked              = rca.get("ranked_causes", [])
        neighbour_escalated = rca_event.get("neighbour_escalated", False) or                               rca.get("neighbour_escalated", False)

        action = deepcopy(REMEDIATION_KB.get(cause, DEFAULT_REMEDIATION))
        action["score"]   = self._score(action, confidence)
        action["summary"] = self._summary(cause, action, cell_id, severity,
                                          neighbour_escalated)

        # For cluster events, prepend a mandatory NOC notification step
        if neighbour_escalated:
            action["steps"] = [
                "CLUSTER ALERT: Notify NOC immediately — multiple adjacent cells affected",
                "Open a P1 incident ticket and assign to senior RF engineer",
            ] + action["steps"]
            action["priority"] = "Critical"
            action["eta_hours"] = max(1, action["eta_hours"] - 1)   # faster SLA

        alternatives = []
        for alt in ranked[1:4]:
            alt_cause  = alt.get("cause", "")
            alt_prob   = float(alt.get("probability", 0)) * 100
            alt_action = deepcopy(REMEDIATION_KB.get(alt_cause, DEFAULT_REMEDIATION))
            alt_action["cause"]       = alt_cause
            alt_action["probability"] = alt.get("probability", 0)
            alt_action["score"]       = self._score(alt_action, alt_prob)
            alternatives.append(alt_action)

        return {
            "cause":               cause,
            "confidence_pct":      confidence,
            "primary_action":      action,
            "alternatives":        alternatives,
            "similar_resolved":    rca.get("similar_incidents", []),
            "neighbour_escalated": neighbour_escalated,
            "is_cluster_event":    neighbour_escalated,
        }


def apply_llm_refinement(
    remediation: dict, llm_out: dict, severity: str, provider: str = ""
) -> dict:
    """
    Merge optional LLM output into base remediation in a guarded manner.
    """
    if not llm_out:
        remediation["llm_enhanced"] = False
        remediation["llm_provider"] = provider or None
        return remediation

    merged = deepcopy(remediation)
    primary = merged.get("primary_action", {})
    revised = llm_out.get("revised_primary_action", {})
    if isinstance(revised, dict):
        allowed = {"action", "steps", "priority", "effort", "eta_hours", "auto", "impact"}
        for k in allowed:
            if k in revised:
                primary[k] = revised[k]
        # Safety guardrail: critical anomalies must stay manual.
        if str(severity).lower() == "critical":
            primary["auto"] = False
    merged["primary_action"] = primary

    merged["llm_enhanced"] = True
    merged["llm_summary"] = llm_out.get("summary", "")
    merged["llm_risk_level"] = llm_out.get("risk_level", "")
    merged["llm_rollback_steps"] = llm_out.get("rollback_steps", [])[:5]
    merged["llm_operator_notes"] = llm_out.get("operator_notes", [])[:5]
    merged["llm_provider"] = provider or None
    return merged


class DashboardState:
    def __init__(self):
        self._lock       = threading.Lock()
        self.events      = deque(maxlen=300)
        self.kpi_history = {}
        self.cell_status = {}
        self.stats       = dict(total_anomalies=0, critical=0, high=0,
                                medium=0, low=0, auto_resolved=0, manual_pending=0)
        self.topology    = self._load_topology()

    @staticmethod
    def _load_topology():
        """Load cell_topology.csv into a list of dicts for the dashboard."""
        if not TOPOLOGY_PATH.exists():
            log.warning(f"Topology file not found at {TOPOLOGY_PATH}")
            return []
        try:
            import csv
            rows = []
            with open(TOPOLOGY_PATH, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    rows.append({
                        "cell_id":     r.get("cell_id", ""),
                        "site_id":     r.get("site_id", ""),
                        "region":      r.get("region", ""),
                        "lat":         float(r.get("latitude", 0) or 0),
                        "lng":         float(r.get("longitude", 0) or 0),
                        "vendor":      r.get("vendor", ""),
                        "band":        r.get("nr_band", ""),
                        "bw":          r.get("bandwidth_MHz", ""),
                        "mimo":        r.get("mimo_config", ""),
                        "slice":       r.get("network_slice", ""),
                        "neighbors":   [n.strip() for n in (r.get("neighbor_cells", "") or "").split(";") if n.strip()],
                        "type":        r.get("deployment_type", ""),
                        "active":      r.get("active", "") == "Yes",
                    })
            log.debug("Topology loaded: %s cells", len(rows))
            return rows
        except Exception as e:
            log.warning(f"Could not load topology: {e}")
            return []

    def push(self, event):
        with self._lock:
            self.events.append(event)
            cell = event.get("cell_id", "")
            sev  = event.get("anomaly_severity", "low")
            snap = event.get("kpi_snapshot", {})
            ts   = event.get("timestamp", "")
            if cell:
                self.cell_status[cell] = sev
                if cell not in self.kpi_history:
                    self.kpi_history[cell] = deque(maxlen=60)
                self.kpi_history[cell].append({
                    "t": ts,
                    "rsrp":    snap.get("RSRP_dBm"),
                    "sinr":    snap.get("SINR_dB"),
                    "prb":     snap.get("PRB_util_DL_pct"),
                    "latency": snap.get("latency_ms"),
                    "tput":    snap.get("throughput_DL_Mbps"),
                    "mos":     snap.get("MOS"),
                })
            self.stats["total_anomalies"] += 1
            if sev in self.stats:
                self.stats[sev] += 1
            act = event.get("remediation", {}).get("primary_action", {})
            if act.get("auto"):
                self.stats["auto_resolved"] += 1
            else:
                self.stats["manual_pending"] += 1

    def snapshot(self):
        with self._lock:
            return {
                "type":        "snapshot",
                "stats":       dict(self.stats),
                "cell_status": dict(self.cell_status),
                "kpi_history": {c: list(h) for c, h in self.kpi_history.items()},
                "events":      list(self.events)[-100:],
                "topology":    self.topology,
            }


STATE      = DashboardState()
WS_CLIENTS = set()
WS_LOCK    = threading.Lock()
WS_LOOP    = None
WS_READY   = threading.Event()


async def ws_handler(websocket):
    with WS_LOCK:
        WS_CLIENTS.add(websocket)
    log.debug("Dashboard connected (%s clients)", len(WS_CLIENTS))
    try:
        await websocket.send(json.dumps(clean_nan(STATE.snapshot()), default=str))
        async for _ in websocket:
            pass
    except Exception:
        pass
    finally:
        with WS_LOCK:
            WS_CLIENTS.discard(websocket)
        log.debug("Dashboard disconnected (%s clients)", len(WS_CLIENTS))


async def _broadcast(msg):
    with WS_LOCK:
        clients = set(WS_CLIENTS)
    if clients:
        await asyncio.gather(*[c.send(msg) for c in clients], return_exceptions=True)


def clean_nan(obj):
    """Recursively replace NaN floats with None so json.dumps never fails."""
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    return obj


def broadcast_event(event):
    if not WS_READY.is_set() or WS_LOOP is None:
        return
    msg = json.dumps(clean_nan({"type": "event", "data": event}), default=str)
    asyncio.run_coroutine_threadsafe(_broadcast(msg), WS_LOOP)


def append_stream_essential(
    *,
    phase: str,
    out: dict,
    remediation: dict,
    llm_used: bool,
) -> None:
    """One compact JSON line per RCA→remediation step (non-redundant with remediation_feed.jsonl)."""
    primary = remediation.get("primary_action") or {}
    rec = {
        "processed_at": out.get("processed_at"),
        "phase": phase,
        "rem_event_id": out.get("rem_event_id"),
        "source_rca_id": out.get("source_rca_id"),
        "timestamp": out.get("timestamp"),
        "cell_id": out.get("cell_id"),
        "severity": out.get("anomaly_severity"),
        "cause": remediation.get("cause"),
        "action": primary.get("action"),
        "auto": bool(primary.get("auto")),
        "llm_enhanced": bool(remediation.get("llm_enhanced")),
        "llm_used_call": llm_used,
    }
    try:
        with open(STREAM_ESSENTIAL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(clean_nan(rec), default=str, ensure_ascii=False) + "\n")
    except OSError as e:
        log.warning("Could not write %s: %s", STREAM_ESSENTIAL_LOG, e)


async def _ws_main(host, port):
    log.debug("WebSocket server ws://%s:%s", host, port)
    async with ws_serve(ws_handler, host, port):
        WS_READY.set()
        await asyncio.Future()


def start_ws_thread(host, port):
    global WS_LOOP
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    WS_LOOP = loop
    loop.run_until_complete(_ws_main(host, port))


def start_http_server(port):
    os.chdir(DASHBOARD_DIR)
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args): pass
    with socketserver.TCPServer(("", port), QuietHandler) as httpd:
        log.debug("HTTP server http://localhost:%s", port)
        httpd.serve_forever()


def prepare_dashboard(ws_port):
    import re
    html_path = DASHBOARD_DIR / "index.html"
    if not html_path.exists():
        log.error(f"Dashboard index.html not found at {html_path}")
        log.error("Place the dashboard/index.html file in the project root dashboard/ folder.")
        sys.exit(1)
    content = html_path.read_text(encoding="utf-8")
    # Replace either the __WS_PORT__ placeholder or a previously injected port number
    content = re.sub(
        r'const WS_PORT\s*=\s*(?:__WS_PORT__|\d+)\s*;',
        f'const WS_PORT = {ws_port};',
        content
    )
    html_path.write_text(content, encoding="utf-8")
    log.debug("Dashboard patched -> %s", html_path)


class FeedReader:
    def __init__(self, llm_advisor=None, llm_provider: str = ""):
        self.engine = RemediationEngine()
        self.llm_advisor = llm_advisor
        self.llm_provider = llm_provider
        self.count  = 0

    def _process(self, line, phase):
        line = line.strip()
        if not line:
            return
        try:
            rca_event = json.loads(line)
        except json.JSONDecodeError:
            return

        self.count += 1
        remediation = self.engine.recommend(rca_event)
        llm_attempted = self.llm_advisor is not None
        if self.llm_advisor is not None:
            llm_out = self.llm_advisor.enrich(rca_event, remediation)
            remediation = apply_llm_refinement(
                remediation=remediation,
                llm_out=llm_out,
                severity=rca_event.get("anomaly_severity", "medium"),
                provider=self.llm_provider,
            )

        out = {
            "rem_event_id":     f"REM-{self.count:07d}",
            "agent":            "RemediationAgent",
            "phase":            phase,
            "processed_at":     datetime.utcnow().isoformat() + "Z",
            "source_rca_id":    rca_event.get("rca_event_id", ""),
            "timestamp":        rca_event.get("timestamp", ""),
            "cell_id":          rca_event.get("cell_id", ""),
            "site_id":          rca_event.get("site_id", ""),
            "region":           rca_event.get("region", ""),
            "vendor":           rca_event.get("vendor", ""),
            "nr_band":          rca_event.get("nr_band", ""),
            "network_slice":    rca_event.get("network_slice", ""),
            "anomaly_severity": rca_event.get("anomaly_severity", ""),
            "anomaly_score":    rca_event.get("anomaly_score"),
            "kpi_snapshot":     rca_event.get("kpi_snapshot", {}),
            "rule_engine":      rca_event.get("rule_engine", {}),
            "rca":              rca_event.get("rca", {}),
            "remediation":      remediation,
        }

        with open(REMEDIATION_FEED, "a", encoding="utf-8") as f:
            f.write(json.dumps(clean_nan(out), default=str) + "\n")

        STATE.push(out)
        broadcast_event(out)

        append_stream_essential(
            phase=phase,
            out=out,
            remediation=remediation,
            llm_used=llm_attempted,
        )

        sev   = str(out["anomaly_severity"] or "").upper()
        cause = remediation["cause"]
        act   = remediation["primary_action"]
        mode  = "[AUTO]" if act["auto"] else "[MANUAL]"
        tag   = "[!!]" if sev in ("HIGH", "CRITICAL") else "[ ~ ]"
        clog("%s [%s] %s | %s | %s %s", tag, sev, out["cell_id"], cause, act["action"], mode)

    def run(self, tail_interval):
        REMEDIATION_FEED.write_text("", encoding="utf-8")
        STREAM_ESSENTIAL_LOG.write_text("", encoding="utf-8")
        pos = 0

        if RCA_FEED.exists():
            clog("Catch-up: reading existing rca_feed.jsonl …")
            with open(RCA_FEED, "r", encoding="utf-8") as f:
                lines = f.readlines()
                pos   = f.tell()
            clog("Catch-up: %s RCA lines", f"{len(lines):,}")
            for line in lines:
                self._process(line, "catch-up")
            clog("Catch-up done, %s events processed", f"{self.count:,}")
        else:
            log.warning("rca_feed.jsonl not found at %s — waiting for Agent 2 …", RCA_FEED)

        clog("Live tail (Ctrl+C to stop)")
        while True:
            try:
                if RCA_FEED.exists():
                    with open(RCA_FEED, "r", encoding="utf-8") as f:
                        f.seek(pos)
                        new_lines = f.readlines()
                        pos = f.tell()
                    for line in new_lines:
                        self._process(line, "live")
                time.sleep(tail_interval)
            except KeyboardInterrupt:
                print("\n  Feed reader stopped.", flush=True)
                break


def parse_args():
    p = argparse.ArgumentParser(description="QoSBuddy - RemediationAgent (Agent 3)")
    p.add_argument("--ws-port",       type=int,   default=8765)
    p.add_argument("--http-port",     type=int,   default=8088)
    p.add_argument("--tail-interval", type=float, default=1.0)
    p.add_argument("--no-browser",    action="store_true")
    p.add_argument(
        "--llm-backend",
        choices=["none", "ollama", "gemini"],
        default="none",
        help="LLM backend: none | ollama (local) | gemini (API key from env)",
    )
    p.add_argument("--use-llm",       action="store_true",
                   help="Shortcut: same as --llm-backend ollama (legacy)")
    p.add_argument("--llm-model",     type=str, default="llama3.1:8b",
                   help="Ollama model name when using --llm-backend ollama")
    p.add_argument("--gemini-model",  type=str, default="gemini-2.0-flash",
                   help="Gemini model id when using --llm-backend gemini")
    p.add_argument("--ollama-url",    type=str, default="http://localhost:11434/api/generate",
                   help="Ollama generate endpoint")
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed logs to the terminal (default: quiet console, full detail in logs/)",
    )
    return p.parse_args()


def main():
    args = parse_args()
    _configure_logging(args.verbose)
    clog("ws-port=%s http-port=%s", args.ws_port, args.http_port)

    prepare_dashboard(args.ws_port)

    ws_thread = threading.Thread(target=start_ws_thread, args=("localhost", args.ws_port), daemon=True)
    ws_thread.start()
    clog("Waiting for WebSocket server …")
    WS_READY.wait(timeout=10)
    if not WS_READY.is_set():
        log.error("WebSocket server did not start. Exiting.")
        sys.exit(1)
    clog("WebSocket ready")

    http_thread = threading.Thread(target=start_http_server, args=(args.http_port,), daemon=True)
    http_thread.start()
    time.sleep(0.2)

    url = f"http://localhost:{args.http_port}"
    if not args.no_browser:
        webbrowser.open(url)

    backend = args.llm_backend
    if args.use_llm and backend == "none":
        backend = "ollama"

    llm_advisor = None
    llm_provider = ""
    llm_label = "off"
    if backend == "ollama":
        llm_provider = "ollama"
        llm_advisor = OllamaRemediationAdvisor(
            model=args.llm_model,
            endpoint=args.ollama_url,
        )
        llm_label = f"ollama ({args.llm_model})"
        clog("LLM: ollama model=%s", args.llm_model)
    elif backend == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            log.warning(
                "GEMINI_API_KEY / GOOGLE_API_KEY not set — LLM disabled (rules only). "
                "PowerShell: $env:GEMINI_API_KEY = 'your_key'"
            )
            llm_label = "off (no API key)"
        else:
            llm_provider = "gemini"
            llm_advisor = GeminiRemediationAdvisor(
                api_key=api_key,
                model=args.gemini_model,
            )
            llm_label = f"gemini ({args.gemini_model})"
            clog("LLM: gemini model=%s", args.gemini_model)
    else:
        llm_label = "off (rules only)"
        clog("LLM: disabled")

    print(
        f"\n  Dashboard       {url}\n"
        f"  WebSocket       ws://localhost:{args.ws_port}\n"
        f"  LLM             {llm_label}\n"
        f"  Stream summary  {STREAM_ESSENTIAL_LOG}\n"
        f"  Full audit log  {LOG_DIR / 'remediation_agent.log'}\n"
        f"  Console detail  {'on (--verbose)' if args.verbose else 'off — add --verbose for trace'}\n",
        flush=True,
    )

    FeedReader(llm_advisor=llm_advisor, llm_provider=llm_provider).run(
        tail_interval=args.tail_interval
    )


if __name__ == "__main__":
    main()