import dash
from dash import dcc, html, dash_table
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import os

# ── Load data ──────────────────────────────────────────────────────────────────
CSV_PATH = os.path.join(os.path.dirname(__file__), "qos_dataset.csv")
df = pd.read_csv(CSV_PATH)

SCENARIOS = df["scenario"].unique().tolist()
SCENARIO_COLORS = {
    "normal":      "#00d4aa",
    "congested":   "#f59e0b",
    "high_loss":   "#ef4444",
    "high_jitter": "#a855f7",
    "critical":    "#ff2d55",
}

SCENARIO_COLORS_RGBA = {
    "normal":      "rgba(0,212,170,0.2)",
    "congested":   "rgba(245,158,11,0.2)",
    "high_loss":   "rgba(239,68,68,0.2)",
    "high_jitter": "rgba(168,85,247,0.2)",
    "critical":    "rgba(255,45,85,0.2)",
}

# ── KPI cards ──────────────────────────────────────────────────────────────────
def kpi_card(title, value, unit, color):
    return html.Div([
        html.P(title, style={"margin": "0 0 6px 0", "fontSize": "11px",
                             "letterSpacing": "2px", "textTransform": "uppercase",
                             "color": "#8892a4"}),
        html.Div([
            html.Span(value, style={"fontSize": "32px", "fontWeight": "700",
                                    "color": color, "fontFamily": "'Space Mono', monospace"}),
            html.Span(f" {unit}", style={"fontSize": "13px", "color": "#8892a4", "marginLeft": "4px"}),
        ]),
    ], style={
        "background": "#0f1923",
        "border": f"1px solid {color}33",
        "borderLeft": f"3px solid {color}",
        "borderRadius": "8px",
        "padding": "18px 22px",
        "flex": "1",
        "minWidth": "160px",
        "boxShadow": f"0 0 20px {color}11",
    })

normal_df = df[df["scenario"] == "normal"]
avg_latency  = round(df["latency_ms"].mean(), 2)
avg_loss     = round(df["packet_loss_pct"].mean(), 2)
avg_jitter   = round(df["jitter_ms"].mean(), 2)
avg_tput     = round(df[df["throughput_mbps"] < 1000]["throughput_mbps"].mean(), 2)

# ── Figures ────────────────────────────────────────────────────────────────────

# 1. Boxplot — latency per scenario
fig_latency = go.Figure()
for sc in SCENARIOS:
    sub = df[df["scenario"] == sc]
    fig_latency.add_trace(go.Box(
        y=sub["latency_ms"], name=sc,
        marker_color=SCENARIO_COLORS.get(sc, "#fff"),
        line_color=SCENARIO_COLORS.get(sc, "#fff"),
        fillcolor=SCENARIO_COLORS_RGBA.get(sc, "rgba(255,255,255,0.1)"),
    ))
fig_latency.update_layout(
    title="Latency Distribution per Scenario (ms)",
    paper_bgcolor="#0a1520", plot_bgcolor="#0a1520",
    font=dict(color="#c9d1d9", family="Space Mono"),
    title_font_size=14,
    showlegend=False,
    yaxis=dict(gridcolor="#1e2d3d", zerolinecolor="#1e2d3d"),
    xaxis=dict(gridcolor="#1e2d3d"),
    margin=dict(l=40, r=20, t=50, b=40),
)

# 2. Boxplot — jitter per scenario
fig_jitter = go.Figure()
for sc in SCENARIOS:
    sub = df[df["scenario"] == sc]
    fig_jitter.add_trace(go.Box(
        y=sub["jitter_ms"], name=sc,
        marker_color=SCENARIO_COLORS.get(sc, "#fff"),
        line_color=SCENARIO_COLORS.get(sc, "#fff"),
        fillcolor=SCENARIO_COLORS_RGBA.get(sc, "rgba(255,255,255,0.1)"),
    ))
fig_jitter.update_layout(
    title="Jitter Distribution per Scenario (ms)",
    paper_bgcolor="#0a1520", plot_bgcolor="#0a1520",
    font=dict(color="#c9d1d9", family="Space Mono"),
    title_font_size=14,
    showlegend=False,
    yaxis=dict(gridcolor="#1e2d3d", zerolinecolor="#1e2d3d"),
    xaxis=dict(gridcolor="#1e2d3d"),
    margin=dict(l=40, r=20, t=50, b=40),
)

# 3. Bar — packet loss per scenario
loss_means = df.groupby("scenario")["packet_loss_pct"].mean().reset_index()
fig_loss = go.Figure(go.Bar(
    x=loss_means["scenario"],
    y=loss_means["packet_loss_pct"],
    marker_color=[SCENARIO_COLORS.get(s, "#fff") for s in loss_means["scenario"]],
    marker_line_width=0,
))
fig_loss.update_layout(
    title="Average Packet Loss per Scenario (%)",
    paper_bgcolor="#0a1520", plot_bgcolor="#0a1520",
    font=dict(color="#c9d1d9", family="Space Mono"),
    title_font_size=14,
    yaxis=dict(gridcolor="#1e2d3d", zerolinecolor="#1e2d3d"),
    xaxis=dict(gridcolor="#1e2d3d"),
    margin=dict(l=40, r=20, t=50, b=40),
)

# 4. Heatmap — latency per src/dst pair per scenario
pivot = df.groupby(["scenario", "src"])["latency_ms"].mean().unstack(fill_value=0)
fig_heatmap = go.Figure(go.Heatmap(
    z=pivot.values,
    x=pivot.columns.tolist(),
    y=pivot.index.tolist(),
    colorscale=[[0, "#0a1520"], [0.5, "#00d4aa"], [1, "#ff2d55"]],
    showscale=True,
))
fig_heatmap.update_layout(
    title="Avg Latency Heatmap (Scenario × Source Host)",
    paper_bgcolor="#0a1520", plot_bgcolor="#0a1520",
    font=dict(color="#c9d1d9", family="Space Mono"),
    title_font_size=14,
    margin=dict(l=80, r=20, t=50, b=40),
)

# 5. Radar — multi-metric per scenario
categories = ["Latency", "Jitter", "Packet Loss", "Throughput (inv)"]
fig_radar = go.Figure()
for sc in SCENARIOS:
    sub = df[df["scenario"] == sc]
    tput = sub[sub["throughput_mbps"] < 1000]["throughput_mbps"].mean()
    tput_inv = max(0, 100 - tput) if not pd.isna(tput) else 100
    vals = [
        min(sub["latency_ms"].mean(), 100),
        min(sub["jitter_ms"].mean(), 100),
        sub["packet_loss_pct"].mean(),
        tput_inv,
    ]
    vals += [vals[0]]
    fig_radar.add_trace(go.Scatterpolar(
        r=vals,
        theta=categories + [categories[0]],
        fill='toself',
        name=sc,
        line_color=SCENARIO_COLORS.get(sc, "#fff"),
        fillcolor=SCENARIO_COLORS_RGBA.get(sc, "rgba(255,255,255,0.1)"),
    ))
fig_radar.update_layout(
    polar=dict(
        bgcolor="#0a1520",
        radialaxis=dict(visible=True, gridcolor="#1e2d3d", color="#8892a4"),
        angularaxis=dict(gridcolor="#1e2d3d", color="#8892a4"),
    ),
    paper_bgcolor="#0a1520",
    font=dict(color="#c9d1d9", family="Space Mono"),
    title="QoS Multi-Metric Radar per Scenario",
    title_font_size=14,
    legend=dict(bgcolor="#0f1923", bordercolor="#1e2d3d", borderwidth=1),
    margin=dict(l=40, r=40, t=60, b=40),
)

# ── Network topology figure ────────────────────────────────────────────────────
node_x = [0.1, 0.1, 0.9, 0.9, 0.3, 0.7, 0.5]
node_y = [0.8, 0.2, 0.8, 0.2, 0.5, 0.5, 0.5]
node_labels = ["h1", "h2", "h3", "h4", "s1", "s2", "s3"]
node_colors = ["#00d4aa","#00d4aa","#a855f7","#a855f7","#f59e0b","#f59e0b","#ef4444"]
edges = [(0,4),(1,4),(2,5),(3,5),(4,6),(5,6)]

edge_x, edge_y = [], []
for a, b in edges:
    edge_x += [node_x[a], node_x[b], None]
    edge_y += [node_y[a], node_y[b], None]

fig_topo = go.Figure()
fig_topo.add_trace(go.Scatter(
    x=edge_x, y=edge_y, mode='lines',
    line=dict(color="#1e2d3d", width=2), hoverinfo='none'
))
fig_topo.add_trace(go.Scatter(
    x=node_x, y=node_y, mode='markers+text',
    marker=dict(size=28, color=node_colors, line=dict(width=2, color="#0a1520")),
    text=node_labels, textposition="middle center",
    textfont=dict(color="#0a1520", size=11, family="Space Mono"),
    hoverinfo='text',
))
fig_topo.update_layout(
    paper_bgcolor="#0a1520", plot_bgcolor="#0a1520",
    showlegend=False,
    xaxis=dict(visible=False), yaxis=dict(visible=False),
    margin=dict(l=0, r=0, t=10, b=0),
    height=220,
    annotations=[
        dict(x=0.1, y=0.95, text="Zone A", showarrow=False,
             font=dict(color="#00d4aa", size=11, family="Space Mono")),
        dict(x=0.9, y=0.95, text="Zone B", showarrow=False,
             font=dict(color="#a855f7", size=11, family="Space Mono")),
        dict(x=0.5, y=0.58, text="Core", showarrow=False,
             font=dict(color="#ef4444", size=10, family="Space Mono")),
    ]
)

# ── App layout ─────────────────────────────────────────────────────────────────
app = dash.Dash(__name__, title="QoSBuddy")

app.layout = html.Div(style={
    "background": "#060d14",
    "minHeight": "100vh",
    "fontFamily": "'Space Mono', monospace",
    "color": "#c9d1d9",
    "padding": "0",
}, children=[

    # Header
    html.Div([
        html.Div([
            html.Span("QoS", style={"color": "#00d4aa"}),
            html.Span("Buddy", style={"color": "#ffffff"}),
        ], style={"fontSize": "26px", "fontWeight": "700", "letterSpacing": "1px"}),
        html.P("Intelligent Network Quality Dashboard",
               style={"margin": "2px 0 0 0", "fontSize": "11px",
                      "color": "#8892a4", "letterSpacing": "3px"}),
    ], style={
        "background": "#0a1520",
        "borderBottom": "1px solid #1e2d3d",
        "padding": "20px 36px",
        "display": "flex", "flexDirection": "column",
    }),

    html.Div(style={"padding": "28px 36px"}, children=[

        # KPI row
        html.Div([
            kpi_card("Avg Latency",     avg_latency,  "ms",  "#00d4aa"),
            kpi_card("Avg Jitter",      avg_jitter,   "ms",  "#a855f7"),
            kpi_card("Avg Packet Loss", avg_loss,     "%",   "#ef4444"),
            kpi_card("Avg Throughput",  avg_tput,     "Mbps","#f59e0b"),
            kpi_card("Scenarios",       len(SCENARIOS),"",   "#38bdf8"),
            kpi_card("Total Samples",   len(df),      "rows","#8892a4"),
        ], style={"display": "flex", "gap": "14px", "flexWrap": "wrap", "marginBottom": "28px"}),

        # Topology + Radar
        html.Div([
            html.Div([
                html.P("VIRTUAL NETWORK TOPOLOGY",
                       style={"fontSize": "10px", "letterSpacing": "2px",
                              "color": "#8892a4", "marginBottom": "8px"}),
                dcc.Graph(figure=fig_topo, config={"displayModeBar": False}),
            ], style={"flex": "1", "background": "#0a1520", "border": "1px solid #1e2d3d",
                      "borderRadius": "10px", "padding": "18px"}),

            html.Div([
                dcc.Graph(figure=fig_radar, config={"displayModeBar": False}, style={"height": "280px"}),
            ], style={"flex": "1", "background": "#0a1520", "border": "1px solid #1e2d3d",
                      "borderRadius": "10px", "padding": "18px"}),
        ], style={"display": "flex", "gap": "14px", "marginBottom": "14px"}),

        # Boxplots row
        html.Div([
            html.Div(dcc.Graph(figure=fig_latency, config={"displayModeBar": False}),
                     style={"flex": "1", "background": "#0a1520", "border": "1px solid #1e2d3d",
                            "borderRadius": "10px", "padding": "10px"}),
            html.Div(dcc.Graph(figure=fig_jitter, config={"displayModeBar": False}),
                     style={"flex": "1", "background": "#0a1520", "border": "1px solid #1e2d3d",
                            "borderRadius": "10px", "padding": "10px"}),
        ], style={"display": "flex", "gap": "14px", "marginBottom": "14px"}),

        # Loss + Heatmap row
        html.Div([
            html.Div(dcc.Graph(figure=fig_loss, config={"displayModeBar": False}),
                     style={"flex": "1", "background": "#0a1520", "border": "1px solid #1e2d3d",
                            "borderRadius": "10px", "padding": "10px"}),
            html.Div(dcc.Graph(figure=fig_heatmap, config={"displayModeBar": False}),
                     style={"flex": "1", "background": "#0a1520", "border": "1px solid #1e2d3d",
                            "borderRadius": "10px", "padding": "10px"}),
        ], style={"display": "flex", "gap": "14px", "marginBottom": "14px"}),

        # Raw data table
        html.Div([
            html.P("RAW DATASET", style={"fontSize": "10px", "letterSpacing": "2px",
                                          "color": "#8892a4", "marginBottom": "12px"}),
            dash_table.DataTable(
                data=df.to_dict("records"),
                columns=[{"name": c, "id": c} for c in df.columns],
                page_size=10,
                sort_action="native",
                filter_action="native",
                style_table={"overflowX": "auto"},
                style_cell={
                    "backgroundColor": "#060d14",
                    "color": "#c9d1d9",
                    "border": "1px solid #1e2d3d",
                    "fontFamily": "Space Mono, monospace",
                    "fontSize": "12px",
                    "padding": "8px 14px",
                },
                style_header={
                    "backgroundColor": "#0f1923",
                    "color": "#00d4aa",
                    "fontWeight": "600",
                    "border": "1px solid #1e2d3d",
                    "letterSpacing": "1px",
                },
                style_data_conditional=[
                    {"if": {"filter_query": '{scenario} = "critical"'},
                     "color": "#ff2d55"},
                    {"if": {"filter_query": '{scenario} = "congested"'},
                     "color": "#f59e0b"},
                    {"if": {"filter_query": '{scenario} = "normal"'},
                     "color": "#00d4aa"},
                ],
            ),
        ], style={"background": "#0a1520", "border": "1px solid #1e2d3d",
                  "borderRadius": "10px", "padding": "20px"}),

    ]),
])

if __name__ == "__main__":
    app.run(debug=True)