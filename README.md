# UrbanPulse Health Assistant

### Project Goal
UrbanPulse is an **Agentic AI prototype** that predicts air quality and urban health risks *before* they occur. Instead of fragmented alerts and static dashboards, UrbanPulse demonstrates turns real-time data into **coordinated district-level action** and **acts autonomously** across buildings, healthcare, and citizens to reduce harm and improve liveability.

UrbanPulse provides real-time health alerts based on Singapore's air quality and environmental data.

### Health Thresholds & Actions
* **PSI 0-50 (Healthy)**: No action needed.
* **PSI 51-100 (Moderate)**: Normal activity; sensitive groups monitor symptoms.
* **PSI > 100 (Unhealthy)**: Automate alert to Polyclinics to prepare masks and resources.


## 🚨 Problem Statement

Singapore already has strong sensors, data, and policies — but responses to air quality, heat, and urban stress remain **reactive and siloed**.

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
