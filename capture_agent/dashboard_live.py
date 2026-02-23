"""
QoSBuddy — Live Dashboard Server (Pure HTML)
KPIs: avg_rtt, p95_rtt, jitter, packet_loss, throughput_down, throughput_up,
      bandwidth_utilization, retransmission_rate, response_time, availability
Run alongside capture_agent.py — opens at http://127.0.0.1:8051
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, csv, statistics

CSV_PATH   = "qos_realtraffic.csv"
MAX_BW_MBPS = 100.0  # your connection's max bandwidth — adjust if needed

# ── local IP prefix to detect down vs up direction
LOCAL_PREFIXES = ("192.168.", "10.", "172.")

def is_local(ip):
    return any(ip.startswith(p) for p in LOCAL_PREFIXES)

def load_csv():
    if not os.path.isfile(CSV_PATH):
        return []
    rows = []
    try:
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append(row)
    except Exception:
        pass
    return rows

def safe_float(v, default=0.0):
    try: return float(v or default)
    except: return default

def percentile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(round((len(s) - 1) * p))
    idx = max(0, min(idx, len(s) - 1))
    return s[idx]

def build_chart_data(rows):
    if not rows:
        return {"total_flows": 0, "total_windows": 0}

    # ── group by window
    by_window = {}
    for r in rows:
        wid = r.get("window_id", "0")
        if wid not in by_window:
            by_window[wid] = []
        by_window[wid].append(r)

    sorted_wids = sorted(by_window.keys(), key=lambda x: int(x or 0))
    recent_wids = sorted_wids[-60:]
    windows_data = [by_window[w] for w in recent_wids]

    # ── per-window aggregated metrics
    wids         = recent_wids
    avg_rtt_list = []
    p95_rtt_list = []
    jitter_list  = []
    loss_list    = []
    tput_down    = []
    tput_up      = []
    retrans_list = []
    quality_list = []

    total_windows_all = len(sorted_wids)
    good_windows      = 0

    for wrows in windows_data:
        first = wrows[0]

        # active ping metrics
        rtt  = safe_float(first.get("ping_google_latency_ms"))
        cfrtt= safe_float(first.get("ping_cloudflare_latency_ms"))
        gwrtt= safe_float(first.get("ping_gateway_latency_ms"))
        rtts = [x for x in [rtt, cfrtt, gwrtt] if x > 0]
        avg_rtt = round(statistics.mean(rtts), 2) if rtts else 0.0
        avg_rtt_list.append(avg_rtt)

        # p95 rtt — approximated from all 3 targets
        p95 = round(percentile(rtts, 0.95), 2)
        p95_rtt_list.append(p95)

        jit = safe_float(first.get("ping_google_jitter_ms"))
        jitter_list.append(round(jit, 2))

        loss = safe_float(first.get("ping_google_loss_pct"))
        loss_list.append(round(loss, 2))

        # throughput down = bw of flows where dst is local (inbound)
        # throughput up   = bw of flows where src is local (outbound)
        down = sum(safe_float(r.get("bandwidth_mbps")) for r in wrows if is_local(r.get("dst_ip", "")))
        up   = sum(safe_float(r.get("bandwidth_mbps")) for r in wrows if is_local(r.get("src_ip", "")))
        tput_down.append(round(down, 3))
        tput_up.append(round(up, 3))

        # retransmission rate — average across TCP flows
        ret_vals = [safe_float(r.get("retrans_rate_pct")) for r in wrows
                    if r.get("protocol") == "TCP"]
        retrans_list.append(round(statistics.mean(ret_vals), 2) if ret_vals else 0.0)

        ql = first.get("quality_label", "good")
        quality_list.append(ql)
        if ql == "good":
            good_windows += 1

    # ── global KPIs
    all_rtts   = [safe_float(r.get("ping_google_latency_ms")) for r in rows if safe_float(r.get("ping_google_latency_ms")) > 0]
    avg_rtt_g  = round(statistics.mean(all_rtts), 2) if all_rtts else 0.0
    p95_rtt_g  = round(sorted(all_rtts)[int(len(all_rtts)*0.95)], 2) if all_rtts else 0.0
    all_jitter = [safe_float(r.get("ping_google_jitter_ms")) for r in rows]
    avg_jitter = round(statistics.mean(all_jitter), 2) if all_jitter else 0.0
    avg_loss   = round(statistics.mean([safe_float(r.get("ping_google_loss_pct")) for r in rows]), 2)

    # bandwidth utilization % = (down+up) / max_bw * 100
    bw_util_list = [round((d+u)/MAX_BW_MBPS*100, 1) for d,u in zip(tput_down, tput_up)]
    avg_bw_util  = round(statistics.mean(bw_util_list), 1) if bw_util_list else 0.0

    # retransmission global
    avg_retrans = round(statistics.mean(retrans_list), 2) if retrans_list else 0.0

    # availability = % of windows with quality != bad
    availability = round(good_windows / total_windows_all * 100, 1) if total_windows_all else 100.0

    # response_time — use avg RTT as proxy (most realistic without HTTP active)
    response_time = avg_rtt_g

    # throughput totals
    avg_down = round(statistics.mean(tput_down), 3) if tput_down else 0.0
    avg_up   = round(statistics.mean(tput_up), 3)   if tput_up   else 0.0

    # ── traffic type distribution
    type_counts = {}
    for r in rows:
        tt = r.get("traffic_type", "unknown")
        type_counts[tt] = type_counts.get(tt, 0) + 1

    # ── bandwidth by type over windows
    bw_by_type = {}
    for wid, wrows in zip(recent_wids, windows_data):
        for r in wrows:
            tt = r.get("traffic_type", "unknown")
            if tt not in bw_by_type:
                bw_by_type[tt] = {}
            bw = safe_float(r.get("bandwidth_mbps"))
            bw_by_type[tt][wid] = bw_by_type[tt].get(wid, 0) + bw

    # ── last 20 flows
    last_flows = rows[-20:][::-1]

    # ── latest window snapshot
    latest = by_window[sorted_wids[-1]][0] if sorted_wids else {}
    alerts = []
    if avg_rtt_g > 120:
        alerts.append(f"High RTT: {avg_rtt_g} ms")
    if avg_loss > 2:
        alerts.append(f"Packet loss: {avg_loss} %")
    if avg_jitter > 20:
        alerts.append(f"High jitter: {avg_jitter} ms")
    return {
         "alerts": alerts,
        "wids": wids,
        "avg_rtt":   avg_rtt_list,
        "p95_rtt":   p95_rtt_list,
        "jitter":    jitter_list,
        "loss":      loss_list,
        "tput_down": tput_down,
        "tput_up":   tput_up,
        "bw_util":   bw_util_list,
        "retrans":   retrans_list,
        "quality":   quality_list,
        "type_counts": type_counts,
        "bw_by_type":  bw_by_type,
        "last_flows":  last_flows,
        "latest":      latest,
        "total_flows":   len(rows),
        "total_windows": total_windows_all,
        # global KPI values
        "kpi": {
            "avg_rtt":      avg_rtt_g,
            "p95_rtt":      p95_rtt_g,
            "avg_jitter":   avg_jitter,
            "avg_loss":     avg_loss,
            "avg_down":     avg_down,
            "avg_up":       avg_up,
            "bw_util":      avg_bw_util,
            "retrans":      avg_retrans,
            "availability": availability,
            "response_time":response_time,
        }
    }

HTML_PAGE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>QoSBuddy Live</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#060D14;color:#C9D1D9;font-family:Consolas,monospace}
  .header{background:#0A1520;border-bottom:1px solid #1E2D3D;padding:14px 28px;
          display:flex;justify-content:space-between;align-items:center}
  .htitle{font-size:20px;font-weight:700}
  .teal{color:#00D4AA}.live{color:#FF2D55;font-size:12px;margin-left:10px;letter-spacing:3px}
  .hsub{font-size:9px;color:#8892A4;letter-spacing:2px;margin-top:3px}
  .upd{font-size:10px;color:#8892A4;display:flex;align-items:center;gap:8px}
  .dot{width:9px;height:9px;border-radius:50%;background:#00D4AA;
       animation:pulse 1.5s infinite;display:inline-block}
  @keyframes pulse{
    0%{opacity:1;box-shadow:0 0 0 0 rgba(0,212,170,.6)}
    70%{opacity:.7;box-shadow:0 0 0 5px rgba(0,212,170,0)}
    100%{opacity:1;box-shadow:0 0 0 0 rgba(0,212,170,0)}}
  .content{padding:16px 24px}
  .kpi-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
  .kpi{background:#0A1520;border-radius:6px;padding:12px 14px;flex:1;min-width:110px}
  .kpi-label{font-size:8px;letter-spacing:2px;text-transform:uppercase;color:#8892A4;margin-bottom:3px}
  .kpi-val{font-size:24px;font-weight:700}
  .kpi-unit{font-size:10px;color:#8892A4;margin-left:2px}
  .kpi-sub{font-size:8px;color:#8892A4;margin-top:2px}
  .row{display:flex;gap:10px;margin-bottom:10px}
  .card{background:#0A1520;border:1px solid #1E2D3D;border-radius:8px;padding:10px;flex:1}
  .ctitle{font-size:8px;letter-spacing:2px;color:#8892A4;margin-bottom:6px;text-transform:uppercase}
  table{width:100%;border-collapse:collapse;font-size:10px}
  th{background:#0F1923;color:#00D4AA;padding:5px 8px;text-align:left;
     border:1px solid #1E2D3D;font-size:9px;letter-spacing:1px;white-space:nowrap}
  td{padding:5px 8px;border:1px solid #1E2D3D;color:#C9D1D9;
     max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .q-good td{color:#00D4AA}.q-degraded td{color:#F59E0B}.q-bad td{color:#EF4444}
  #waiting{text-align:center;margin-top:80px;color:#8892A4;font-size:14px}
</style>
</head>
<body>
<div class="header">
  <div>
    <div class="htitle"><span class="teal">QoS</span>Buddy<span class="live">LIVE</span></div>
    <div class="hsub">Real-Time Network Quality Monitor</div>
  </div>
  <div class="upd"><div class="dot"></div><span id="ts">Connecting...</span></div>
</div>
<div class="content">
  <div id="waiting" style="display:none">⏳ Waiting for data... Make sure capture_agent.py is running.</div>
  <div id="dash">
    <div class="kpi-row" id="kpis"></div>
    <div id="alerts" style="margin:10px 0;"></div>
    <div class="row">
      <div class="card" style="flex:2"><div class="ctitle">RTT — avg &amp; p95 (ms)</div><div id="c-rtt"></div></div>
      <div class="card" style="flex:1"><div class="ctitle">Packet Loss %</div><div id="c-loss"></div></div>
    </div>
    <div class="row">
      <div class="card" style="flex:1"><div class="ctitle">Throughput Down / Up (Mbps)</div><div id="c-tput"></div></div>
      <div class="card" style="flex:1"><div class="ctitle">Bandwidth Utilization %</div><div id="c-bwutil"></div></div>
      <div class="card" style="flex:1"><div class="ctitle">Retransmission Rate %</div><div id="c-retrans"></div></div>
    </div>
    <div class="row">
      <div class="card" style="flex:2"><div class="ctitle">Bandwidth by Traffic Type (Mbps)</div><div id="c-bw"></div></div>
      <div class="card" style="flex:1"><div class="ctitle">Traffic Distribution</div><div id="c-pie"></div></div>
    </div>
    <div class="row">
      <div class="card"><div class="ctitle">Quality Timeline</div><div id="c-qual"></div></div>
    </div>
    <div class="row">
      <div class="card"><div class="ctitle">Live Flows — Last 20</div><div id="flows"></div></div>
    </div>
  </div>
</div>
<script>
const TC={dns:"#00D4AA",https:"#A855F7",http:"#F59E0B",voip_webrtc:"#38BDF8",
  streaming_udp:"#F472B6",email:"#34D399",icmp_probe:"#8892A4",
  tcp_other:"#6366F1",udp_other:"#FB923C",ssh:"#FBBF24",dhcp:"#A3E635",
  no_traffic:"#1E2D3D",unknown:"#8892A4"};
const QC={good:"#00D4AA",degraded:"#F59E0B",bad:"#EF4444"};
const QN={good:3,degraded:2,bad:1};
const BASE={paper_bgcolor:"#0A1520",plot_bgcolor:"#0A1520",
  font:{color:"#C9D1D9",family:"Consolas",size:10},
  margin:{l:40,r:10,t:8,b:30},
  yaxis:{gridcolor:"#1E2D3D",zerolinecolor:"#1E2D3D"},
  xaxis:{gridcolor:"#1E2D3D",zerolinecolor:"#1E2D3D"}};
const CFG={displayModeBar:false,responsive:true};

function kpi(label,val,unit,color,sub){
  return `<div class="kpi" style="border-left:3px solid ${color}">
    <div class="kpi-label">${label}</div>
    <div><span class="kpi-val" style="color:${color}">${val}</span><span class="kpi-unit">${unit}</span></div>
    <div class="kpi-sub">${sub}</div></div>`;}

function render(d){
  const k=d.kpi||{};
  const ql=(d.latest||{}).quality_label||"good";
  const qc=QC[ql]||"#00D4AA";

    const a = d.alerts || [];
  document.getElementById("alerts").innerHTML =
    a.length
      ? `<div style="padding:10px;border:1px solid #EF4444;border-radius:8px;color:#EF4444;background:#0A1520">
           ⚠️ Alerts: ${a.join(" | ")}
         </div>`
      : `<div style="padding:10px;border:1px solid #1E2D3D;border-radius:8px;color:#34D399;background:#0A1520">
           ✅ Status: OK
         </div>`;

  // ── KPI row
  document.getElementById("kpis").innerHTML=
    kpi("Avg RTT",        k.avg_rtt,    "ms",  "#00D4AA","multi-target ping")+
    kpi("P95 RTT",        k.p95_rtt,    "ms",  "#A855F7","95th percentile")+
    kpi("Jitter",         k.avg_jitter, "ms",  "#38BDF8","ping variation")+
    kpi("Packet Loss",    k.avg_loss,   "%",   "#EF4444","avg loss")+
    kpi("Throughput ↓",   k.avg_down,   "Mbps","#00D4AA","download")+
    kpi("Throughput ↑",   k.avg_up,     "Mbps","#F472B6","upload")+
    kpi("BW Utilization", k.bw_util,    "%",   "#F59E0B","of 100Mbps max")+
    kpi("Retransmissions",k.retrans,    "%",   "#FB923C","TCP retrans rate")+
    kpi("Availability",   k.availability,"%",  "#34D399","good windows")+
    kpi("Response Time",  k.response_time,"ms","#FBBF24","avg RTT proxy")+
    kpi("Quality",        ql.toUpperCase(),"",  qc,      "current window")+
    kpi("Total Flows",    d.total_flows, "",   "#8892A4",d.total_windows+" windows");

  // ── RTT chart
  Plotly.react("c-rtt",[
    {x:d.wids,y:d.avg_rtt,name:"Avg RTT",type:"scatter",mode:"lines",
     line:{color:"#00D4AA",width:2},fill:"tozeroy",fillcolor:"rgba(0,212,170,0.08)"},
    {x:d.wids,y:d.p95_rtt,name:"P95 RTT",type:"scatter",mode:"lines",
     line:{color:"#A855F7",width:1.5,dash:"dot"}},
    {x:d.wids,y:d.jitter,name:"Jitter",type:"scatter",mode:"lines",
     line:{color:"#38BDF8",width:1.5,dash:"dash"}}],
    {...BASE,height:200,legend:{bgcolor:"#0A1520",bordercolor:"#1E2D3D",
     borderwidth:1,font:{size:9},orientation:"h",y:-0.35}},CFG);

  // ── Loss chart
  Plotly.react("c-loss",[
    {x:d.wids,y:d.loss,type:"bar",
     marker:{color:d.quality.map(q=>QC[q]||"#00D4AA")},name:"Loss%"}],
    {...BASE,height:200,showlegend:false},CFG);

  // ── Throughput chart
  Plotly.react("c-tput",[
    {x:d.wids,y:d.tput_down,name:"Down",type:"scatter",mode:"lines",
     line:{color:"#00D4AA",width:2},fill:"tozeroy",fillcolor:"rgba(0,212,170,0.08)"},
    {x:d.wids,y:d.tput_up,name:"Up",type:"scatter",mode:"lines",
     line:{color:"#F472B6",width:2},fill:"tozeroy",fillcolor:"rgba(244,114,182,0.08)"}],
    {...BASE,height:180,legend:{bgcolor:"#0A1520",bordercolor:"#1E2D3D",
     borderwidth:1,font:{size:9}}},CFG);

  // ── BW Utilization
  Plotly.react("c-bwutil",[
    {x:d.wids,y:d.bw_util,type:"scatter",mode:"lines",
     line:{color:"#F59E0B",width:2},fill:"tozeroy",fillcolor:"rgba(245,158,11,0.08)"}],
    {...BASE,height:180,showlegend:false,
     yaxis:{...BASE.yaxis,range:[0,100]}},CFG);

  // ── Retransmission
  Plotly.react("c-retrans",[
    {x:d.wids,y:d.retrans,type:"bar",
     marker:{color:"#FB923C"},name:"Retrans%"}],
    {...BASE,height:180,showlegend:false},CFG);

  // ── Traffic pie
  const types=Object.keys(d.type_counts);
  Plotly.react("c-pie",[
    {labels:types,values:Object.values(d.type_counts),type:"pie",hole:0.4,
     marker:{colors:types.map(t=>TC[t]||"#8892A4"),line:{color:"#060D14",width:2}},
     textinfo:"label+percent",textfont:{size:9,color:"#fff"}}],
    {...BASE,height:240,showlegend:false,margin:{l:5,r:5,t:5,b:5}},CFG);

  // ── BW by type
  const topT=types.sort((a,b)=>d.type_counts[b]-d.type_counts[a]).slice(0,5);
  Plotly.react("c-bw",topT.map(tt=>{
    const bwD=d.bw_by_type[tt]||{};
    return{x:d.wids,y:d.wids.map(w=>bwD[w]||0),name:tt,type:"scatter",mode:"lines",
      line:{color:TC[tt]||"#8892A4",width:1.5},
      fill:"tozeroy",fillcolor:"rgba(0,0,0,0.08)"};
  }),{...BASE,height:240,legend:{bgcolor:"#0A1520",bordercolor:"#1E2D3D",
    borderwidth:1,font:{size:9},orientation:"h",y:-0.3}},CFG);

  // ── Quality timeline
  Plotly.react("c-qual",[
    {x:d.wids,y:d.quality.map(q=>QN[q]||3),type:"scatter",mode:"lines+markers",
     line:{color:"#F59E0B",width:2},
     marker:{color:d.quality.map(q=>QC[q]||"#00D4AA"),size:6}}],
    {...BASE,height:160,showlegend:false,
     yaxis:{tickvals:[1,2,3],ticktext:["BAD","DEGRADED","GOOD"],
            gridcolor:"#1E2D3D",zerolinecolor:"#1E2D3D"}},CFG);

  // ── Live flows table
  const cols=["timestamp","traffic_type","src_ip","dst_ip","protocol","dst_port",
    "bandwidth_mbps","passive_jitter_ms","retrans_rate_pct","quality_label"];
  const avail=d.last_flows.length?cols.filter(c=>c in d.last_flows[0]):cols;
  let html=`<table><thead><tr>${avail.map(c=>`<th>${c}</th>`).join("")}</tr></thead><tbody>`;
  d.last_flows.forEach(r=>{
    const ql=r.quality_label||"good";
    const ts=(r.timestamp||"").split("T")[1]||r.timestamp||"";
    const row={...r,timestamp:ts.split(".")[0]};
    html+=`<tr class="q-${ql}">${avail.map(c=>`<td title="${row[c]||""}">${row[c]||""}</td>`).join("")}</tr>`;
  });
  html+="</tbody></table>";
  document.getElementById("flows").innerHTML=html;
}

async function refresh(){
  try{
    const res=await fetch("/data");
    const d=await res.json();
    document.getElementById("ts").textContent="Last update: "+new Date().toLocaleTimeString();
    if(!d.total_flows){
      document.getElementById("waiting").style.display="block";
    }else{
      document.getElementById("waiting").style.display="none";
      render(d);
    }
  }catch(e){document.getElementById("ts").textContent="Error: "+e.message;}
}
refresh();
setInterval(refresh,5000);
</script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif self.path == "/data":
            rows = load_csv()
            data = build_chart_data(rows)
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data, default=str).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    print("=" * 50)
    print("  QoSBuddy Live Dashboard")
    print("  Open: http://127.0.0.1:8051")
    print("  Make sure capture_agent.py is running!")
    print("=" * 50)
    HTTPServer(("127.0.0.1", 8051), Handler).serve_forever()
