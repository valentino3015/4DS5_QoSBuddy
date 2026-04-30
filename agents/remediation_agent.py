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
import webbrowser, http.server, socketserver, warnings, math, csv, re
from pathlib import Path
from datetime import datetime, timezone
from collections import deque
from copy import deepcopy
import requests

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

# Knowledge Base (Deprecated in favor of AI)
DEFAULT_REMEDIATION = {
    "action": "Manual investigation required",
    "steps": [
        "Check LLM service availability",
        "Collect full OMC performance counters for the affected cell",
        "Review the alarm history for the past 24 hours",
        "Escalate to the Level-2 RF engineering team"
    ],
    "priority": "Medium", "effort": "High", "eta_hours": 8, "auto": False,
    "summary": "The LLM API is unavailable. Defaulting to manual investigation.",
    "impact": "Requires manual analysis to determine the correct resolution path"
}

def get_llm_port():
    app_py_path = ROOT / "LLM" / "App.py"
    if app_py_path.exists():
        content = app_py_path.read_text(encoding="utf-8")
        match = re.search(r'port\s*=\s*(\d+)', content)
        if match:
            return int(match.group(1))
    return 8081

LLM_PORT = get_llm_port()


class RemediationEngine:
    def __init__(self):
        self.cache_file = OUTPUT_DIR / "llm_cache.jsonl"
        self.cache = {}
        if self.cache_file.exists():
            try:
                for line in self.cache_file.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line: continue
                    entry = json.loads(line)
                    self.cache[entry["cache_key"]] = entry["data"]
            except Exception as e:
                log.warning(f"Could not load LLM cache: {e}")

    def _append_to_cache(self, cache_key, data):
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            entry = {"cache_key": cache_key, "data": data}
            with open(self.cache_file, "a", encoding='utf-8') as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.warning(f"Could not append to LLM cache: {e}")

    def recommend(self, rca_event):
        rca                 = rca_event.get("rca", {})
        cause               = rca.get("primary_cause", "Unknown")
        confidence          = float(rca.get("confidence_pct", 50.0))
        severity            = rca_event.get("anomaly_severity", "LOW").upper()
        cell_id             = rca_event.get("cell_id", "unknown")
        site_id             = rca_event.get("site_id", "unknown")
        region              = rca_event.get("region", "unknown")
        rca_id              = rca_event.get("rca_event_id", "unknown")
        neighbour_escalated = rca_event.get("neighbour_escalated", False) or rca.get("neighbour_escalated", False)
        vendor              = rca_event.get("vendor", "unknown")
        band                = rca_event.get("nr_band", "unknown")

        cache_key = f"{cause}::{severity}::{vendor}::{band}"
        llm_data = None
        
        # Check if we should try reconnecting to the LLM API
        if not getattr(self, "_llm_available", True) and time.time() > getattr(self, "_llm_next_retry", 0):
            log.info("Cooldown passed. Attempting to reconnect to Mistral AI API...")
            self._llm_available = True

        if cache_key in self.cache:
            log.info(f"LLM Cache Hit for [{cache_key}] - Skipping Mistral AI API.")
            cached = deepcopy(self.cache[cache_key])
            llm_data = cached["llm_data"]
            # Swap dynamic fields
            sum_text = llm_data.get("summary", "")
            sum_text = sum_text.replace(cached["orig_cell"], cell_id)
            sum_text = sum_text.replace(cached["orig_rca_id"], rca_id)
            sum_text = sum_text.replace(cached["orig_site"], site_id)
            sum_text = sum_text.replace(cached["orig_region"], region)
            llm_data["summary"] = sum_text
            
            if "incident_info" in llm_data:
                llm_data["incident_info"]["cell"] = cell_id
                llm_data["incident_info"]["site"] = site_id
                llm_data["incident_info"]["region"] = region
                llm_data["incident_info"]["score"] = rca_event.get("anomaly_score", 0.0)
        elif not getattr(self, "_llm_available", True):
            # If we already determined the LLM is down, skip to fallback instantly
            pass
        else:
            url = f"http://127.0.0.1:{LLM_PORT}/predict"
            safe_event = clean_nan(rca_event)
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    response = requests.post(url, json=safe_event, timeout=600.0)
                    if response.status_code == 200:
                        data = response.json()
                        if "error" in data:
                            log.warning(f"LLM returned error: {data['error']} (attempt {attempt}/{max_retries})")
                        elif "response" in data:
                            llm_data = data["response"]
                            cache_entry = {
                                "orig_cell": cell_id,
                                "orig_site": site_id,
                                "orig_region": region,
                                "orig_rca_id": rca_id,
                                "llm_data": llm_data
                            }
                            self.cache[cache_key] = cache_entry
                            self._append_to_cache(cache_key, cache_entry)
                            break  # success
                        elif "raw_response" in data:
                            log.warning("LLM API returned raw_response instead of structured JSON.")
                    else:
                        log.warning(f"LLM API returned HTTP {response.status_code} (attempt {attempt}/{max_retries})")
                except requests.exceptions.ConnectionError as e:
                    log.warning("LLM API is unreachable. Disabling queries for 60s to prevent freezing.")
                    self._llm_available = False
                    self._llm_next_retry = time.time() + 60
                    break
                except requests.exceptions.RequestException as e:
                    log.warning(f"LLM API request failed ({e}) — attempt {attempt}/{max_retries}")
                
                # Exponential backoff before retry (if not disabled)
                if getattr(self, "_llm_available", True) and attempt < max_retries:
                    backoff = 3 ** attempt  # 3s, 9s
                    log.info(f"  Retrying in {backoff}s ...")
                    time.sleep(backoff)
        if llm_data:
            info = llm_data.get("incident_info", {})
            steps = llm_data.get("remediation_steps", [])
            
            raw_eta = str(info.get("eta", "8"))
            parsed_eta = re.sub(r'[^0-9]', '', raw_eta)
            eta_val = int(parsed_eta) if parsed_eta else 8
            
            action = {
                "summary": llm_data.get("summary", "No summary available."),
                "steps": steps,
                "action": steps[0] if (steps and isinstance(steps, list)) else "Auto-generated investigation",
                "auto": str(info.get("mode", "Manual")).lower() == "auto",
                "eta_hours": eta_val,
                "priority": info.get("severity", "Medium"),
                "impact": "Implements exact instructions listed in remediation steps."
            }
            alts = []
            for alt in llm_data.get("alternative_causes", []):
                raw_conf = str(alt.get("confidence_pct", 0.0)).replace("%", "").strip()
                try:
                    conf_val = float(raw_conf) / 100.0
                except ValueError:
                    conf_val = 0.0

                alts.append({
                    "cause": alt.get("cause", "Unknown alternative"),
                    "probability": conf_val,
                    "action": "Alternative proposed fix",
                    "priority": "Low",
                    "eta_hours": 8
                })
        else:
            action = deepcopy(DEFAULT_REMEDIATION)
            alts = []
            
        # For cluster events, prepend a mandatory NOC notification step
        if neighbour_escalated:
            action["steps"] = [
                "CLUSTER ALERT: Notify NOC immediately \u2014 multiple adjacent cells affected",
                "Open a P1 incident ticket and assign to senior RF engineer",
            ] + action.get("steps", [])
            action["priority"] = "Critical"
            action["eta_hours"] = max(1, action.get("eta_hours", 2) - 1)
            
        return {
            "cause":               cause,
            "confidence_pct":      confidence,
            "primary_action":      action,
            "alternatives":        alts,
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
        self.events      = deque()  # no maxlen — keep all events for full history
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
            # Return only the last 2000 events to prevent browser memory crashes
            # 18,000+ events in a single WebSocket message will stall most browsers.
            recent_events = list(self.events)[-2000:]
            return {
                "type":        "snapshot",
                "stats":       dict(self.stats),
                "cell_status": dict(self.cell_status),
                "kpi_history": {c: list(h) for c, h in self.kpi_history.items()},
                "events":      recent_events, 
                "topology":    self.topology,
                "full_history_count": len(self.events)
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
        clients = list(WS_CLIENTS)
    for client in clients:
        try:
            # Sequential send prevents the "AssertionError" drain clash on Windows
            await client.send(msg)
        except Exception:
            # If a client is disconnected/stalled, don't crash the broadcast for others
            continue


def clean_nan(obj):
    """Recursively replace NaN floats with None so json.dumps never fails."""
    if isinstance(obj, float):
        return None if math.isnan(obj) else obj
    if isinstance(obj, (str, int, bool, type(None))):
        return obj
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
    log.info(f"WebSocket server on ws://{host}:{port}")
    # Disable ping_interval to stop the "keepalive ping failed" noise on Windows
    async with ws_serve(ws_handler, host, port, ping_interval=None):
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
    def __init__(
        self,
        llm_advisor=None,
        llm_provider: str = "",
        *,
        llm_on_catch_up: bool = False,
    ):
        self.engine = RemediationEngine()
        self.llm_advisor = llm_advisor
        self.llm_provider = llm_provider
        self.llm_on_catch_up = llm_on_catch_up
        self.count  = 0
        self._feed_fh = None  # persistent file handle for remediation_feed

    def _ensure_feed_handle(self):
        if self._feed_fh is None:
            REMEDIATION_FEED.parent.mkdir(parents=True, exist_ok=True)
            self._feed_fh = open(REMEDIATION_FEED, "a", encoding="utf-8")
        return self._feed_fh

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


        run_llm = (
            self.llm_advisor is not None and
            phase == "live" and
            rca_event.get("anomaly_severity", "").lower() in ["high", "critical"]
            )

        llm_out = self.llm_advisor.enrich(rca_event, remediation) if run_llm else None
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
            "processed_at":     datetime.now(timezone.utc).isoformat(),
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

        fh = self._ensure_feed_handle()
        fh.write(json.dumps(clean_nan(out), default=str) + "\n")
        fh.flush()

        STATE.push(out)
        
        # Only broadcast to live dashboards during the LIVE phase.
        # Broadcasting 18,000 events during catch-up will overflow WebSocket buffers.
        if phase == "live":
            broadcast_event(out)

        sev   = out["anomaly_severity"].upper()
        cause = remediation.get("cause", "")
        act   = remediation.get("primary_action", {})
        mode  = "[AUTO]" if act.get("auto") else "[MANUAL]"
        tag   = "[!!]" if sev in ("HIGH", "CRITICAL") else "[ ~ ]"
        log.info(f"{tag} [{sev:<8s}] {out['cell_id']:<14s} | {cause} | {act.get('action', '')} {mode}")

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

        log.info("=" * 60)
        log.info("PHASE 2 - LIVE TAIL  (Ctrl+C to stop)")
        log.info("=" * 60)

        try:
            with open(RCA_FEED, "r", encoding="utf-8") as tail_fh:
                tail_fh.seek(pos)
                while True:
                    line = tail_fh.readline()
                    if line:
                        self._process(line, "live")
                    else:
                        # Detect if the DetectionAgent truncated the file
                        try:
                            if tail_fh.tell() > RCA_FEED.stat().st_size:
                                log.warning("Feed truncated! Resetting tail to beginning.")
                                tail_fh.seek(0)
                                continue
                        except Exception:
                            pass
                        time.sleep(tail_interval)
        except KeyboardInterrupt:
            log.info("Feed reader stopped.")
        finally:
            if self._feed_fh:
                self._feed_fh.close()


def parse_args():
    p = argparse.ArgumentParser(description="QoSBuddy - RemediationAgent (Agent 3)")
    p.add_argument("--ws-port",       type=int,   default=8765)
    p.add_argument("--http-port",     type=int,   default=8080)
    p.add_argument("--tail-interval", type=float, default=0.6) 
    p.add_argument("--no-browser",    action="store_true")
    p.add_argument(
        "--llm-backend",
        choices=["none", "ollama", "gemini", "phi2"],
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
    p.add_argument(
        "--llm-on-catch-up",
        action="store_true",
        help="Call the LLM for every historical line during catch-up (default: LLM only on new live lines; avoids API floods)",
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
    elif backend == "phi2":
        llm_provider = "phi2-local"
        llm_advisor = LocalPhi2Advisor()
        llm_label = "phi-2 (fine-tuned)"
    
    else:
        llm_label = "off (rules only)"
        clog("LLM: disabled")

    llm_catch = bool(llm_advisor and args.llm_on_catch_up)
    print(
        f"\n  Dashboard       {url}\n"
        f"  WebSocket       ws://localhost:{args.ws_port}\n"
        f"  LLM             {llm_label}\n"
        f"  LLM catch-up    {'on (--llm-on-catch-up)' if llm_catch else 'off (live tail only — use --llm-on-catch-up to enrich history)'}\n"
        f"  Stream summary  {STREAM_ESSENTIAL_LOG}\n"
        f"  Full audit log  {LOG_DIR / 'remediation_agent.log'}\n"
        f"  Console detail  {'on (--verbose)' if args.verbose else 'off — add --verbose for trace'}\n",
        flush=True,
    )

    FeedReader(
        llm_advisor=llm_advisor,
        llm_provider=llm_provider,
        llm_on_catch_up=args.llm_on_catch_up,
    ).run(tail_interval=args.tail_interval)


if __name__ == "__main__":
    main()