# QoSBuddy
## AI-Driven Predictive Quality of Service Monitoring and Optimization System

---

## Project Information

**Project Duration:** 12 Weeks  
**Status:** In Preparation  

---

## Team Members

- Mariem Gharbi  
- Hadyle Zribi  
- Donia Hali  
- Mariam Ben Abdallah  
- Omar Zallila  
- Ahmed Abid  

---

## 1. Overview

QoSBuddy is an AI-driven system designed to monitor, predict, and optimize **Network Quality of Service (QoS)** in real time.

Modern communication networks support critical services such as VoIP, cloud applications, video streaming, and real-time systems. Maintaining stable performance in terms of:

- Latency  
- Jitter  
- Packet Loss  
- Throughput  
- Bandwidth Utilization  

is essential to ensure reliability, user satisfaction, and compliance with Service Level Agreements (SLAs).

Unlike traditional monitoring tools that focus primarily on reactive detection, QoSBuddy introduces predictive analytics and intelligent optimization capabilities to proactively prevent service degradation.

### The system provides:

- Real-time anomaly detection  
- Predictive QoS analytics  
- Intelligent resource optimization recommendations  
- Interactive dashboards and automated AI-generated reports  

---

## 2. Project Objectives

### BO1 — QoS Monitoring

**Business Objective (BO)**  
Continuously assess and track the health of network services.

**Data Science Objective (DSO)**  
Design a QoS health scoring model that summarizes multiple network metrics into a single service quality indicator.

**Key Metrics**
- QoS Health Score (0–100)
- Service availability (%)
- Metric stability (variance over time)

**Models**
- **EWMA** → Smooths short-term fluctuations in real-time metrics  
- **Hidden Markov Models (HMM)** → Models service states (Good / Degraded / Critical)  
- **K-Means Clustering** → Groups similar QoS behavior patterns  

---

### BO2 — QoS Detection & Prediction

**Business Objective (BO)**  
Detect QoS degradations early and anticipate future performance issues to minimize service impact.

**Data Science Objective (DSO)**  
Develop anomaly detection and time-series forecasting models for user-side QoS data.

**Key Metrics**
- Latency (RTT)
- Jitter
- Packet Loss (%)
- Short-term predicted latency (t+1, t+5, t+10)
- Degradation risk score

**Models**
- **Isolation Forest** → Unsupervised anomaly detection on noisy QoS data  
- **Autoencoder** → Learns normal QoS patterns and flags deviations  
- **One-Class SVM** → Detects anomalies when only normal data is available  
- **LSTM / GRU** → Captures temporal dependencies in QoS time-series  
- **ARIMA** → Interpretable statistical baseline for forecasting  

---

### BO3 — Autonomous QoS Optimization

**Business Objective (BO)**  
Automatically optimize network performance to maintain SLA compliance while minimizing operational cost.

**Data Science Objective (DSO)**  
Develop a prescriptive optimization engine that dynamically adjusts routing, bandwidth allocation, and resource scaling based on predicted QoS risks.

**Key Metrics**
- QoS improvement after action (%)
- SLA violation reduction rate
- Mean Time to Recovery (MTTR)

**Models**
- **Reinforcement Learning (DQN / Policy Gradient)** → Learns optimal network adjustment policies through feedback  
- **Genetic Algorithms** → Finds near-optimal routing and allocation strategies under constraints  
- **Linear / Constrained Optimization** → Ensures SLA, bandwidth, and cost constraints are respected  
- **Multi-Armed Bandit** → Dynamically selects the best optimization strategy  

---

### BO4 — QoS Reporting & Insights

**Business Objective (BO)**  
Provide clear and actionable QoS insights for decision-makers.

**Data Science Objective (DSO)**  
Develop explainable analytics models that translate technical QoS metrics into business-level insights.

**Key Metrics**
- SLA compliance (%)
- Mean degradation duration
- Incident frequency

**Models**
- **Decision Trees** → Human-readable explanations  
- **XGBoost** → Identifies key QoS impact factors with high accuracy  
- **SHAP** → Explains model predictions and root causes  

## 3. System Architecture

QoSBuddy follows an Agent-Based Architecture composed of specialized components:

| Agent | Responsibility |
|--------|----------------|
| Monitoring Agent | Collects real-time QoS metrics |
| Analysis Agent | Performs anomaly detection |
| Prediction Agent | Forecasts QoS degradation |
| Reporting Agent | Generates AI-based analytical reports |
| Coordinator Agent | Manages escalation and optimization workflows |

Agents can be deployed centrally or distributed across network nodes depending on infrastructure requirements.

---

## 4. Target Users

- Telecommunication Companies  
- Internet Service Providers (ISPs)  
- Large Enterprises and Corporate Networks  
- Data Centers and Cloud Providers  
- Academic and Research Institutions  

---

## 5. Sustainable Development Impact

QoSBuddy contributes to the following Sustainable Development Goals (SDGs):

- SDG 9 – Industry, Innovation and Infrastructure  
- SDG 11 – Sustainable Cities and Communities  
- SDG 12 – Responsible Consumption and Production  
- SDG 8 – Decent Work and Economic Growth  

By optimizing bandwidth utilization and reducing service disruptions, the system promotes more sustainable and resilient digital infrastructures.

---

## 6. Methodology

The project follows the Team Data Science Process (TDSP):

1. Business Understanding  
2. Data Acquisition and Exploration  
3. Modeling  
4. Deployment  
5. Continuous Improvement  

---

## 7. Core Features

### Real-Time Monitoring
- Latency, jitter, packet loss, and throughput tracking  
- Application-level performance monitoring  

### Predictive Analytics
- Congestion forecasting  
- SLA violation prediction  

### Automated Optimization
- Dynamic routing recommendations  
- Bandwidth allocation strategies  

### Alerting and Notifications
- Threshold-based alerts  
- Email and dashboard notifications  

### Visualization and Reporting
- Heatmaps  
- Predictive performance graphs  
- Automated AI-generated analytical reports  

### Multi-Environment Support
- Cloud environments  
- On-premises infrastructures  
- IoT-based networks  

---

## 8. Non-Functional Requirements

- High scalability  
- Low processing latency  
- 24/7 availability  
- Secure data handling  
- Modular and maintainable architecture  

---

## 9. Differentiation

QoSBuddy distinguishes itself from traditional monitoring tools by emphasizing:

- Predictive rather than purely reactive monitoring  
- AI-driven optimization mechanisms  
- Automated root cause analysis  
- Cross-environment intelligence  
- Sustainability-aware decision support  

---

## 10. Project Scope

This prototype focuses on:

- Software-based QoS monitoring and analytics  
- AI-driven decision support systems  
- Simulation and SDN-based optimization  

Physical hardware deployment is outside the scope of this academic prototype.

---

## 11. UI Prototype

Figma Design:  
https://www.figma.com/make/xUVuGo2nDWkZcw2MV2WSfV/QoSBuddy-System-Pages

---

## 12. Planned Technology Stack

- Python  
- Kafka  
- Spark or Flink  
- Scikit-learn  
- TensorFlow or PyTorch  
- Streamlit or Dash  
- Docker  

---

## 13. Dataset

Primary Benchmark Dataset:

- UNSW-NB15  

---

## 14. Future Vision

- Industrial deployment readiness  
- Edge AI agents  
- Energy-aware optimization  
- SDN controller integration  
- SaaS-based platform version  

---

## 15. License

Educational and Research Prototype  

---

## 16. Contributions

This project is developed as part of an academic initiative.  
Research collaborations and improvement proposals are welcome.