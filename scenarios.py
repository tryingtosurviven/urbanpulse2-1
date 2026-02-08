# scenarios.py
"""
Demo scenarios for UrbanPulse presentation.
These allow you to control the demo without relying on live data.

Each scenario represents a different air quality situation in Singapore,
with PSI values for all 5 regions (central, east, north, south, west).
"""

DEMO_SCENARIOS = {
    "low_haze": {
        "psi_data": {
            "central": 65,
            "east": 60,
            "north": 55,
            "south": 62,
            "west": 68
        },
        "description": "Low haze detected - Early warning",

    },
    
    "moderate_haze": {
        "psi_data": {
            "central": 125,
            "east": 118,
            "north": 95,
            "south": 102,
            "west": 130
        },
        "description": "Moderate haze event - Protocol activated"
    },
    
    "severe_haze": {
        "psi_data": {
            "central": 215,
            "east": 198,
            "north": 185,
            "south": 205,
            "west": 225
        },
        "description": "Severe haze crisis - Full emergency response"
    }
}

# PSI Reference Guide (for your presentation):
# 0-50:   Good (Green)
# 51-100: Moderate (Blue)
# 101-200: Unhealthy (Orange/Red)
# 201-300: Very Unhealthy (Purple)
# 301+:   Hazardous (Maroon)
