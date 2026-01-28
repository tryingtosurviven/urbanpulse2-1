# UrbanPulse Health Assistant

### Project Goal
UrbanPulse is an **Agentic AI prototype** that predicts air quality and urban health risks *before* they occur. Instead of fragmented alerts and static dashboards, UrbanPulse demonstrates turns real-time data into **coordinated district-level action** and **acts autonomously** across buildings, healthcare, and citizens to reduce harm and improve liveability.

UrbanPulse provides real-time health alerts based on Singapore's air quality and environmental data.

### Health Thresholds & Actions
* **PSI 0-50 (Healthy)**: No action needed.
* **PSI 51-100 (Moderate)**: Normal activity; sensitive groups monitor symptoms.
* **PSI > 100 (Unhealthy)**: Automate alert to Polyclinics to prepare masks and resources.

### Technical Setup
The backend is a Flask API (nea_agent.py) hosted on IBM Cloud. It fetches data from NEA's API to monitor the Environment.

