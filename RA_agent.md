# Prediction & Risk Assessment Agent — Reference Knowledge

## Purpose
This agent forecasts district-level PM2.5/PSI, converts predictions into health risk levels, and generates a trigger payload for downstream actions.

## Data policy
- Live air quality data is NOT stored in knowledge.
- Live PSI/PM2.5 must be fetched via tools (API calls).
- If a field is missing, return null. Do not guess.

## Health thresholds
- PSI 0–50: Healthy → no action
- PSI 51–100: Moderate → advisory (optional)
- PSI > 100: Unhealthy → trigger clinic readiness + HVAC recycle mode

Early warning (optional):
- If predicted PSI increases by ≥20% within 2 hours AND confidence ≥0.7 → pre-emptive action allowed.

## Input schema (from Environment Monitoring Agent)
Required:
- timestamp
- district
- psi_current OR pm25_current
- wind_speed
- wind_direction
Optional:
- humidity, temperature
- spike_flag (true/false)
- spike_magnitude (%)

## Output schema (to Action Execution + Policy Orchestrator)
Return JSON with:
- forecast: [{district, time_window, pm25_pred, psi_pred, confidence}]
- risk: [{district, risk_level: Healthy|Moderate|Unhealthy, notes}]
- trigger: {trigger_actions: true/false, actions: [], priority, reason_codes: []}

## Action mapping
If Unhealthy:
- actions include: ["ALERT_CLINIC", "HVAC_RECYCLE_MODE", "CITIZEN_NUDGE"]
If Moderate:
- actions include: ["CITIZEN_NUDGE"] (optional)
