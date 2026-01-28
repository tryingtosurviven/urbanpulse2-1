# UrbanPulse Health Assistant

### Project Goal
UrbanPulse is an **Agentic AI prototype** that predicts air quality and urban health risks *before* they occur. Instead of fragmented alerts and static dashboards, UrbanPulse demonstrates turns real-time data into **coordinated district-level action** and **acts autonomously** across buildings, healthcare, and citizens to reduce harm and improve liveability.

UrbanPulse provides real-time health alerts based on Singapore's air quality and environmental data.

### Health Thresholds & Actions
* **PSI 0-50 (Healthy)**: No action needed.
* **PSI 51-100 (Moderate)**: Normal activity; sensitive groups monitor symptoms.
* **PSI > 100 (Unhealthy)**: Automate alert to Polyclinics to prepare masks and resources.

## 🧩 Agent Architecture (watsonx Orchestrate)

UrbanPulse is implemented as a **multi-agent system** using **IBM watsonx Orchestrate**, where each agent has a clear responsibility and operates autonomously under orchestration.

### Core Agents
### 1. Environment Monitoring Agent
- Ingests live and simulated data from data.gov.sg
- Monitors air quality (PSI / PM₂.₅), weather, wind direction, and humidity
- Detects abnormal pollution or environmental spikes
- Sends structured signals to the prediction agent

### 2. Prediction & Risk Assessment Agent
- Runs machine learning models to forecast haze movement and severity
- Predicts PM₂.₅ spikes by district and time window
- Translates environmental signals into health risk levels
- Triggers downstream actions when thresholds are exceeded

### 3. Action Execution Agent
- Executes autonomous responses based on predicted risk
- Triggers HVAC systems to switch to *Recycle Mode*
- Sends automated alerts to polyclinics and facilities managers
- Issues non-identifying public nudges and recommendations
- Logs all executed actions for traceability

### 4. Policy & Orchestrator Agent
- Coordinates all agents within watsonx Orchestrate
- Enforces health, safety, and fairness constraints
- Approves, blocks, or modifies actions before execution
- Maintains audit logs and ensures explainable decisions

Each action executed by UrbanPulse is the result of **agent-to-agent reasoning and orchestration**, not a single rule-based script.


UrbanPulse addresses the missing layer:  
**AI agents that predict, negotiate, and execute actions automatically across systems.**


## 🧠 System Overview

UrbanPulse is built using a **three-layer agentic architecture**.

### Layer 1: Live Data (Simulated)
- Weather (wind speed & direction)
- Hyper-local air quality sensors (synthetic spikes)
- Data sourced from **data.gov.sg** and augmented for demo realism

### Layer 2: AI Prediction (“The Brain”)
- Predicts haze movement and PM₂.₅ spikes by district
- Estimates respiratory health risk surges
- Implemented using `RandomForestRegressor` (scikit-learn)
- Model accuracy metrics shown during demo

### Layer 3: Autonomous Action (“Smart Response”)
Using **IBM watsonx Orchestrate**, the system acts without human input:
- Triggers HVAC systems to switch to *Recycle Mode*
- Alerts polyclinics to prepare for asthma surges
- Sends automated facility and logistics nudges
- Logs all actions for auditability

---

## 🤖 Why This Is Agentic AI

UrbanPulse demonstrates **high autonomy and agency**:
- **Predicts** risk before impact
- **Acts** without human prompts
- **Adapts** as conditions improve or worsen
- **Coordinates** multiple agents under policy constraints

This is not “AI + alerts” — it is **agent-to-agent negotiation and execution**.


## 🛠️ Tech Stack
The backend is a Flask API (nea_agent.py) hosted on IBM Cloud. It fetches data from NEA's API to monitor the Environment.

- Python + FastAPI  
- scikit-learn (ML prediction)  
- IBM watsonx Orchestrate (agent orchestration)  
- data.gov.sg (open datasets)  
- matplotlib (live visualization)


## 🎥 Demo Flow

1. Pull live data from data.gov.sg  
2. Show AI predicting a haze or heat risk  
3. Show watsonx Orchestrate automatically executing responses  
4. Display action logs and explanations  



## 📌 Repository

https://github.com/shaira44444/urbanpulse

