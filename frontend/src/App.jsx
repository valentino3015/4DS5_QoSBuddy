import { useState } from "react";
import "./App.css";

function App() {
  const [page, setPage] = useState("home");

  return (
    <div className="app">
      <aside className="sidebar">
        <h2>QoSBuddy</h2>
        <p className="small">Deployment Web App</p>

        <button onClick={() => setPage("home")}>Home</button>
        <button onClick={() => setPage("deployment")}>Deployment</button>
        <button onClick={() => setPage("dashboard")}>Live Dashboard</button>
        <button onClick={() => setPage("about")}>About</button>
      </aside>

      <main className="content">
        {page === "home" && <Home />}
        {page === "deployment" && <Deployment />}
        {page === "dashboard" && <LiveDashboard />}
        {page === "about" && <About />}
      </main>
    </div>
  );
}

function Home() {
  return (
    <section>
      <h1>QoSBuddy Web Application</h1>
      <p>
        QoSBuddy is an AI-based QoS monitoring platform for detecting anomalies,
        predicting risks, and generating remediation recommendations.
      </p>

      <div className="cards">
        <div className="card">
          <h3>Detection</h3>
          <p>Identifies abnormal QoS behavior from network KPI data.</p>
        </div>

        <div className="card">
          <h3>Prediction</h3>
          <p>Estimates future risk levels and possible service degradation.</p>
        </div>

        <div className="card">
          <h3>Recommendations</h3>
          <p>Uses the remediation agent and LLM logic to propose actions.</p>
        </div>
      </div>
    </section>
  );
}

function Deployment() {
  return (
    <section>
      <h1>Deployment Monitor</h1>
      <p>
        This page summarizes how the QoSBuddy system is deployed and how its
        backend agents communicate with the live dashboard.
      </p>

      <div className="cards">
        <div className="card">
          <h3>Detection Agent</h3>
          <p><strong>Status:</strong> Running manually</p>
          <p><strong>Command:</strong></p>
          <code>python agents/detection_agent.py --mode all</code>
        </div>

        <div className="card">
          <h3>Remediation Agent</h3>
          <p><strong>Status:</strong> Running manually</p>
          <p><strong>Command:</strong></p>
          <code>python agents/remediation_agent.py --ws-port 9000 --http-port 9001</code>
        </div>

        <div className="card">
          <h3>React Frontend</h3>
          <p><strong>Status:</strong> Running</p>
          <p><strong>URL:</strong></p>
          <code>http://localhost:5173</code>
        </div>
      </div>

      <div className="flow">
        <h2>Deployment Flow</h2>
        <p>
          Network KPI Data → Detection Agent → RCA Feed → Remediation Agent →
          Existing Live Dashboard → React Web App
        </p>
      </div>
    </section>
  );
}

function LiveDashboard() {
  return (
    <section className="dashboard-section">
      <div className="dashboard-header">
        <div>
          <h1>Live QoSBuddy Dashboard</h1>
          <p>
            The existing live dashboard is embedded here without losing the
            original WebSocket and HTTP functionality.
          </p>
        </div>

        <a
          href="http://127.0.0.1:9001"
          target="_blank"
          rel="noreferrer"
          className="open-link"
        >
          Open original dashboard
        </a>
      </div>

      <iframe
        title="QoSBuddy Live Dashboard"
        src="http://127.0.0.1:9001"
        className="dashboard-frame"
      />
    </section>
  );
}

function About() {
  return (
    <section>
      <h1>About QoSBuddy</h1>
      <p>
        QoSBuddy combines anomaly detection, prediction, root-cause analysis,
        and remediation recommendation into one deployable monitoring system.
      </p>

      <div className="flow">
        <h2>Technology Stack</h2>
        <p>
          Python agents for backend intelligence, WebSocket and HTTP for live
          updates, and React for the final web application interface.
        </p>
      </div>
    </section>
  );
}

export default App;