# UrbanPulse Health Assistant

### Project Goal
UrbanPulse provides real-time health alerts based on Singapore's air quality and environmental data.

### Health Thresholds & Actions
* **PSI 0-50 (Healthy)**: No action needed.
* **PSI 51-100 (Moderate)**: Normal activity; sensitive groups monitor symptoms.
* **PSI > 100 (Unhealthy)**: Automate alert to Polyclinics to prepare masks and resources.

### Technical Setup
The backend is a Flask API (nea_agent.py) hosted on IBM Cloud. It fetches data from NEA's API to monitor the Environment.
