import { useState } from "react";
import "./App.css";

function App() {
  const [page, setPage] = useState("home");

  return (
    <div className="app">
      <nav className="navbar">
        <div>
          <h2>QoSBuddy</h2>
          <p>Deployment Web App</p>
        </div>

        <div className="nav-buttons">
          <button
            className={page === "home" ? "active" : ""}
            onClick={() => setPage("home")}
          >
            Home
          </button>

          <button
            className={page === "dashboard" ? "active" : ""}
            onClick={() => setPage("dashboard")}
          >
            Live Dashboard
          </button>
        </div>
      </nav>

      <main className={page === "dashboard" ? "dashboard-content" : "content"}>
        {page === "home" && <Home />}
        {page === "dashboard" && <LiveDashboard />}
      </main>
    </div>
  );
}

function Home() {
  return (
    <section className="home-page">
      <div className="hero">
        <h1>QoSBuddy Web Application</h1>
        <p>
          QoSBuddy is an AI-based QoS monitoring platform for detecting anomalies,
          predicting risks, and generating remediation recommendations.
        </p>
      </div>

      <div className="cards">
        <div className="card">
          <h3>Detection</h3>
          <p>
            The detection agent analyzes network KPI data and identifies abnormal
            QoS behavior in real time.
          </p>
        </div>

        <div className="card">
          <h3>Prediction</h3>
          <p>
            The prediction module estimates future risk levels and possible
            service degradation.
          </p>
        </div>

        <div className="card">
          <h3>Recommendations</h3>
          <p>
            The remediation agent generates recommendations to help improve
            network quality and reduce incidents.
          </p>
        </div>
      </div>

      <div className="about-section">
        <h2>About QoSBuddy</h2>
        <p>
          QoSBuddy combines anomaly detection, prediction, root-cause analysis,
          and remediation recommendation into one deployable monitoring system.
        </p>

        <div className="flow">
          <h2>Deployment Flow</h2>
          <p>
            Network KPI Data → Detection Agent → RCA Feed → Remediation Agent →
            Live Dashboard → React Web Application
          </p>
        </div>
      </div>
    </section>
  );
}

function LiveDashboard() {
  return (
    <section className="live-dashboard-page">
      <div className="dashboard-top">
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

export default App;