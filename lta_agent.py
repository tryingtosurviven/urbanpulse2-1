# lta_agent.py — UrbanPulse R3 LTA DataMall Integration
# Fetches live traffic speed bands to estimate delivery ETA
# to affected polyclinics after a PO is dispatched.

import os
import time
import requests

LTA_API_KEY = os.getenv("LTA_API_KEY")
LTA_BASE_URL = "https://datamall2.mytransport.sg/ltaodataservice"

# Clinic/hospital coordinates for route matching
FACILITY_LOCATIONS = {
    "ttsh": {
        "name": "Tan Tock Seng Hospital",
        "area": "central",
        "lat": 1.3210,
        "lng": 103.8468,
    },
    "sgh": {
        "name": "Singapore General Hospital",
        "area": "central",
        "lat": 1.2796,
        "lng": 103.8354,
    },
    "jurong": {
        "name": "Jurong Polyclinic",
        "area": "west",
        "lat": 1.3329,
        "lng": 103.7436,
    },
    "woodlands": {
        "name": "Woodlands Polyclinic",
        "area": "north",
        "lat": 1.4361,
        "lng": 103.7865,
    },
    "tampines": {
        "name": "Tampines Polyclinic",
        "area": "east",
        "lat": 1.3525,
        "lng": 103.9447,
    },
}

# Central warehouse origin (Tuas / Pioneer area)
WAREHOUSE = {
    "name": "Central Medical Warehouse (Tuas)",
    "lat": 1.3236,
    "lng": 103.6397,
}

# Speed band → estimated km/h
SPEED_BAND_MAP = {
    "1": 10,   # very slow / jam
    "2": 25,   # slow
    "3": 45,   # moderate
    "4": 65,   # fast
    "5": 80,   # very fast
    "6": 90,   # expressway free flow
    "7": 100,  # max
    "8": 110,  # max expressway
}


def _fetch_traffic_speed_bands() -> list:
    """
    Calls LTA DataMall /TrafficSpeedBands and returns raw band list.
    Falls back to empty list on failure.
    """
    if not LTA_API_KEY:
        return []

    try:
        resp = requests.get(
            f"{LTA_BASE_URL}/v3/TrafficSpeedBands",
            headers={"AccountKey": LTA_API_KEY},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])
    except Exception as e:
        print(f"[LTA] API call failed: {e}")
        return []


def _average_speed_from_bands(bands: list) -> float:
    """
    Averages speed across all returned bands.
    Returns km/h float.
    """
    if not bands:
        return 45.0  # fallback: assume moderate traffic

    speeds = []
    for band in bands:
        raw = str(band.get("SpeedBand", "3"))
        speeds.append(SPEED_BAND_MAP.get(raw, 45))

    return sum(speeds) / len(speeds)


def _estimate_eta_minutes(distance_km: float, avg_speed_kmh: float) -> int:
    """
    Simple ETA = distance / speed, converted to minutes.
    Adds 5 min buffer for loading/unloading.
    """
    if avg_speed_kmh <= 0:
        avg_speed_kmh = 45.0
    travel_minutes = (distance_km / avg_speed_kmh) * 60
    return int(travel_minutes + 5)


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    """
    Straight-line distance between two coordinates in km.
    Good enough for ETA estimation.
    """
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def get_delivery_eta(facility_id: str) -> dict:
    """
    Main function called by app.py after a PO is dispatched.

    Returns:
    {
        "facility": "Tan Tock Seng Hospital",
        "eta_minutes": 23,
        "avg_speed_kmh": 52.3,
        "distance_km": 18.4,
        "live_data": True,
        "route_label": "Central Medical Warehouse → Tan Tock Seng Hospital",
        "display": "⏱ Estimated supply arrival: 23 mins",
        "timestamp": 1234567890
    }
    """
    facility = FACILITY_LOCATIONS.get(facility_id)
    if not facility:
        # Default to TTSH if unknown
        facility = FACILITY_LOCATIONS["ttsh"]

    distance_km = _haversine_km(
        WAREHOUSE["lat"], WAREHOUSE["lng"],
        facility["lat"], facility["lng"]
    )

    bands = _fetch_traffic_speed_bands()
    live_data = len(bands) > 0
    avg_speed = _average_speed_from_bands(bands)
    eta_minutes = _estimate_eta_minutes(distance_km, avg_speed)

    return {
        "facility": facility["name"],
        "eta_minutes": eta_minutes,
        "avg_speed_kmh": round(avg_speed, 1),
        "distance_km": round(distance_km, 1),
        "live_data": live_data,
        "route_label": f"{WAREHOUSE['name']} → {facility['name']}",
        "display": f"⏱ Estimated supply arrival: {eta_minutes} mins",
        "timestamp": int(time.time()),
    }