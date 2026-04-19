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
"""

import os, sys, json, time, logging, argparse, threading, asyncio
import webbrowser, http.server, socketserver, warnings, math
from pathlib import Path
from datetime import datetime
from collections import deque
from copy import deepcopy

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VENDOR_DIR = ROOT / ".vendor"
if VENDOR_DIR.exists() and str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from qosbuddy_llm.inference import QoSBuddyLLM
from qosbuddy_llm.remediation_kb import (
    DEFAULT_REMEDIATION,
    EFFORT_SCORE,
    PRIORITY_SCORE,
    REMEDIATION_KB,
)

warnings.filterwarnings("ignore")

try:
    import websockets
    from websockets.server import serve as ws_serve
except ImportError:
    websockets = None
    ws_serve = None

# Paths
DATA_DIR      = ROOT / "data"
OUTPUT_DIR    = DATA_DIR / "output"
LOG_DIR       = ROOT / "logs"
DASHBOARD_DIR = ROOT / "dashboard"

for d in [OUTPUT_DIR, LOG_DIR, DASHBOARD_DIR]:
    d.mkdir(parents=True, exist_ok=True)

RCA_FEED         = OUTPUT_DIR / "rca_feed.jsonl"
REMEDIATION_FEED = OUTPUT_DIR / "remediation_feed.jsonl"
TOPOLOGY_PATH    = DATA_DIR / "cell_topology.csv"

# Logging
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_sh  = logging.StreamHandler(sys.stdout)
_fh  = logging.FileHandler(LOG_DIR / "remediation_agent.log", encoding="utf-8")
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
_sh.setFormatter(_fmt); _fh.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_sh, _fh])
log = logging.getLogger("RemediationAgent")


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
            log.info(f"  Topology loaded: {len(rows)} cells")
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
    log.info(f"Dashboard connected ({len(WS_CLIENTS)} total)")
    try:
        await websocket.send(json.dumps(clean_nan(STATE.snapshot()), default=str))
        async for _ in websocket:
            pass
    except Exception:
        pass
    finally:
        with WS_LOCK:
            WS_CLIENTS.discard(websocket)
        log.info(f"Dashboard disconnected ({len(WS_CLIENTS)} remaining)")


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


async def _ws_main(host, port):
    log.info(f"WebSocket server on ws://{host}:{port}")
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
        log.info(f"HTTP server on http://localhost:{port}")
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
    log.info(f"Dashboard ready -> {html_path}")


class FeedReader:
    def __init__(self, llm_engine):
        self.engine = RemediationEngine()
        self.llm_engine = llm_engine
        self.count = 0

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
        llm_remediation = self.llm_engine.generate(rca_event, remediation)

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
            "llm_remediation":  llm_remediation,
        }

        with open(REMEDIATION_FEED, "a", encoding="utf-8") as f:
            f.write(json.dumps(clean_nan(out), default=str) + "\n")

        STATE.push(out)
        broadcast_event(out)

        sev   = out["anomaly_severity"].upper()
        cause = remediation["cause"]
        act   = remediation["primary_action"]
        mode  = "[AUTO]" if act["auto"] else "[MANUAL]"
        tag   = "[!!]" if sev in ("HIGH", "CRITICAL") else "[ ~ ]"
        llm_status = llm_remediation.get("source", "unknown")
        log.info(
            f"{tag} [{sev:<8s}] {out['cell_id']:<14s} | {cause} | {act['action']} {mode} | llm={llm_status}"
        )

    def run(self, tail_interval):
        REMEDIATION_FEED.write_text("", encoding="utf-8")
        pos = 0

        if RCA_FEED.exists():
            log.info("=" * 60)
            log.info("PHASE 1 - CATCH-UP")
            log.info("=" * 60)
            with open(RCA_FEED, "r", encoding="utf-8") as f:
                lines = f.readlines()
                pos   = f.tell()
            log.info(f"  Processing {len(lines):,} existing RCA events ...")
            for line in lines:
                self._process(line, "catch-up")
            log.info(f"  Catch-up done ({self.count:,} events processed)")
        else:
            log.warning(f"rca_feed.jsonl not found at {RCA_FEED} - waiting for Agent 2 ...")

        log.info("=" * 60)
        log.info("PHASE 2 - LIVE TAIL  (Ctrl+C to stop)")
        log.info("=" * 60)
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
                log.info("Feed reader stopped.")
                break


def parse_args():
    p = argparse.ArgumentParser(description="QoSBuddy - RemediationAgent (Agent 3)")
    p.add_argument("--ws-port",       type=int,   default=8765)
    p.add_argument("--http-port",     type=int,   default=8080)
    p.add_argument("--tail-interval", type=float, default=1.0)
    p.add_argument("--no-browser",    action="store_true")
    p.add_argument("--disable-llm",   action="store_true")
    p.add_argument("--llm-base-model", type=str, default="Qwen/Qwen2.5-0.5B-Instruct")
    p.add_argument("--llm-adapter-dir", type=str, default=str(ROOT / "models" / "qosbuddy-llm-adapter"))
    p.add_argument("--llm-device", type=str, default="auto")
    p.add_argument("--llm-max-new-tokens", type=int, default=256)
    return p.parse_args()


def main():
    args = parse_args()
    log.info("QoSBuddy RemediationAgent (Agent 3) starting")
    log.info(f"  ws-port={args.ws_port} | http-port={args.http_port}")

    if ws_serve is None:
        log.error("websockets not installed. Run: pip install websockets")
        sys.exit(1)

    if args.disable_llm:
        class DisabledLLM:
            def generate(self, _rca_event, remediation):
                action = remediation.get("primary_action", {})
                return {
                    "model": "QoSBuddy-LLM",
                    "status": "fallback",
                    "source": "disabled",
                    "reason": "disabled by CLI",
                    "explanation": action.get("summary", "QoSBuddy-LLM is disabled."),
                    "priority": action.get("priority", "Medium"),
                    "recommended_action": action.get("action", "Manual investigation required"),
                    "steps": list(action.get("steps", [])),
                    "raw_text": "",
                }

        llm_engine = DisabledLLM()
        log.info("QoSBuddy-LLM disabled by CLI flag")
    else:
        llm_engine = QoSBuddyLLM(
            root_dir=ROOT,
            base_model=args.llm_base_model,
            adapter_dir=args.llm_adapter_dir,
            device=args.llm_device,
            max_new_tokens=args.llm_max_new_tokens,
            logger=log,
        )

    prepare_dashboard(args.ws_port)

    ws_thread = threading.Thread(target=start_ws_thread, args=("localhost", args.ws_port), daemon=True)
    ws_thread.start()
    log.info("Waiting for WebSocket server ...")
    WS_READY.wait(timeout=10)
    if not WS_READY.is_set():
        log.error("WebSocket server did not start. Exiting.")
        sys.exit(1)
    log.info("WebSocket server ready [OK]")

    http_thread = threading.Thread(target=start_http_server, args=(args.http_port,), daemon=True)
    http_thread.start()
    time.sleep(0.2)

    url = f"http://localhost:{args.http_port}"
    if not args.no_browser:
        webbrowser.open(url)

    log.info("=" * 60)
    log.info(f"  Dashboard : {url}")
    log.info(f"  WebSocket : ws://localhost:{args.ws_port}")
    log.info("=" * 60)

    FeedReader(llm_engine).run(tail_interval=args.tail_interval)


if __name__ == "__main__":
    main()
