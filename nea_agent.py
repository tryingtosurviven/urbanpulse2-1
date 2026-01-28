import requests
import os
import pandas as pd
from datetime import datetime, timezone

# =========================================================
# CONFIG
# =========================================================
REALTIME_BASE = "https://api-open.data.gov.sg/v2/real-time/api"
API_KEY = os.getenv("DATA_GOV_SG_API_KEY", "").strip()

SESSION = requests.Session()
DEFAULT_TIMEOUT = 15

# =========================================================
# HELPERS
# =========================================================
def _headers():
    h = {"Accept": "application/json"}
    if API_KEY:
        h["x-api-key"] = API_KEY
    return h


def _safe_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    r = SESSION.get(url, headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


def _parse_iso_dt(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _warn_if_stale(ts_str: str, label: str, max_age_minutes: int):
    dt = _parse_iso_dt(ts_str)
    if not dt:
        return
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now(timezone.utc)
    age_min = (now - dt).total_seconds() / 60.0
    if age_min > max_age_minutes:
        print(f"⚠️ [STALE]: {label} timestamp looks old ({age_min:.0f} min ago): {ts_str}")


def _clean_region_df(df: pd.DataFrame, region_col: str, value_col: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out[region_col] = out[region_col].astype(str).str.strip().str.lower()
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")
    out = out.dropna(subset=[value_col])
    out = out[out[region_col] != "national"]
    return out


# =========================================================
# FETCHER
# =========================================================
def fetch_nea_data(endpoint_name: str):
    url = f"{REALTIME_BASE}/{endpoint_name}"

    try:
        full_data = _safe_get(url)
        data_block = full_data.get("data", {})

        # PSI (region dict)
        if endpoint_name == "psi":
            items_list = data_block.get("items", [])
            if not items_list:
                print("⚠️ [DEBUG]: API returned empty items for psi")
                return pd.DataFrame(), None

            latest_item = items_list[0]
            ts = latest_item.get("timestamp") or latest_item.get("updatedTimestamp")

            readings_obj = latest_item.get("readings", {}) or {}
            psi_24h = readings_obj.get("psi_twenty_four_hourly", {}) or {}

            if not psi_24h:
                print("⚠️ [DEBUG]: PSI readings missing psi_twenty_four_hourly")
                return pd.DataFrame(), ts

            df = pd.DataFrame([{"region": k, "psi": v} for k, v in psi_24h.items()])
            return df, ts

        # PM2.5 (region dict)
        if endpoint_name == "pm25":
            items_list = data_block.get("items", [])
            if not items_list:
                print("⚠️ [DEBUG]: API returned empty items for pm25")
                return pd.DataFrame(), None

            latest_item = items_list[0]
            ts = latest_item.get("timestamp") or latest_item.get("updatedTimestamp")

            readings_obj = latest_item.get("readings", {}) or {}
            pm25_1h = readings_obj.get("pm25_one_hourly", {}) or {}

            if not pm25_1h:
                print("⚠️ [DEBUG]: PM2.5 readings missing pm25_one_hourly")
                return pd.DataFrame(), ts

            df = pd.DataFrame([{"region": k, "pm25": v} for k, v in pm25_1h.items()])
            return df, ts

        # UV (hourly list, island-wide)
        if endpoint_name == "uv":
            records = data_block.get("records", [])
            if not records:
                print("⚠️ [DEBUG]: API returned empty records for uv")
                return pd.DataFrame(), None

            latest = records[0]
            ts = latest.get("timestamp") or latest.get("updatedTimestamp")

            index_list = latest.get("index", []) or []
            if not index_list:
                print("⚠️ [DEBUG]: UV index list missing")
                return pd.DataFrame(), ts

            df = pd.DataFrame(index_list)
            if "value" in df.columns:
                df = df.rename(columns={"value": "uv"})
            return df, ts

        # DEFAULT: station-based weather endpoints
        readings_list = data_block.get("readings", [])
        if not readings_list:
            print(f"⚠️ [DEBUG]: API returned empty readings for {endpoint_name}")
            return pd.DataFrame(), None

        latest_reading = readings_list[0]
        ts = latest_reading.get("timestamp")

        actual_values = latest_reading.get("data", [])
        if isinstance(actual_values, list):
            df = pd.DataFrame(actual_values)
        else:
            df = pd.DataFrame([{"value": actual_values}])

        col_name = endpoint_name.replace("-", "_")
        df = df.rename(columns={"value": col_name})
        return df, ts

    except requests.exceptions.HTTPError as e:
        print(f"❌ [HTTP ERROR] {endpoint_name}: {e}")
    except Exception as e:
        print(f"❌ [UNKNOWN ERROR] {endpoint_name}: {e}")

    return pd.DataFrame(), None


# =========================================================
# MAIN SNAPSHOT FUNCTION (CALLED BY app.py)
# =========================================================
def run_snapshot():
    # Station-based
    temp_df, ts = fetch_nea_data("air-temperature")
    humid_df, _ = fetch_nea_data("relative-humidity")
    wind_dir_df, _ = fetch_nea_data("wind-direction")
    wind_speed_df, _ = fetch_nea_data("wind-speed")
    rain_df, _ = fetch_nea_data("rainfall")

    # Region / special endpoints
    uv_df, uv_ts = fetch_nea_data("uv")        # island-wide
    pm25_df, pm25_ts = fetch_nea_data("pm25")  # by region
    psi_df, psi_ts = fetch_nea_data("psi")     # by region

    # Freshness checks (optional)
    _warn_if_stale(ts, "station weather bundle", max_age_minutes=20)
    _warn_if_stale(pm25_ts, "pm25", max_age_minutes=90)
    _warn_if_stale(psi_ts, "psi", max_age_minutes=90)
    _warn_if_stale(uv_ts, "uv", max_age_minutes=90)

    # UV latest hour (island-wide)
    if not uv_df.empty and "uv" in uv_df.columns:
        uv_df["uv"] = pd.to_numeric(uv_df["uv"], errors="coerce")
        uv_df = uv_df.dropna(subset=["uv"])
        current_uv = float(uv_df.sort_values("hour")["uv"].iloc[-1]) if not uv_df.empty else 0.0
    else:
        current_uv = 0.0

    # PM2.5 avg (exclude national)
    pm25_clean = _clean_region_df(pm25_df, "region", "pm25")
    avg_pm25 = float(pm25_clean["pm25"].mean()) if not pm25_clean.empty else 0.0

    # PSI avg (exclude national)
    psi_clean = _clean_region_df(psi_df, "region", "psi")
    avg_psi = float(psi_clean["psi"].mean()) if not psi_clean.empty else 0.0

    # Merge station data (optional sample)
    merged_rows = []
    if not temp_df.empty and not humid_df.empty:
        final_df = pd.merge(temp_df, humid_df, on="stationId", how="inner")
        if not wind_dir_df.empty:
            final_df = pd.merge(final_df, wind_dir_df, on="stationId", how="inner")
        if not wind_speed_df.empty:
            final_df = pd.merge(final_df, wind_speed_df, on="stationId", how="inner")
        if not rain_df.empty:
            final_df = pd.merge(final_df, rain_df, on="stationId", how="inner")
        merged_rows = final_df.head(10).to_dict(orient="records")

    # Region guidance lists (threshold-based)
    regions_avoid = []
    if not pm25_clean.empty:
        elevated = pm25_clean[pm25_clean["pm25"] > 55].sort_values("pm25", ascending=False)
        for _, row in elevated.iterrows():
            regions_avoid.append({
                "region": row["region"],
                "reason": "pm25_elevated",
                "value": float(row["pm25"]),
                "advice": "Avoid prolonged outdoor activity; consider mask for sensitive groups."
            })

    if not psi_clean.empty:
        unhealthy = psi_clean[psi_clean["psi"] >= 101].sort_values("psi", ascending=False)
        for _, row in unhealthy.iterrows():
            regions_avoid.append({
                "region": row["region"],
                "reason": "psi_unhealthy",
                "value": float(row["psi"]),
                "advice": "Avoid outdoor exercise; sensitive groups stay indoors."
            })

    uv_warning = None
    if current_uv >= 8:
        uv_warning = "Extreme UV island-wide: avoid midday sun, use sunscreen, seek shade."

    return {
        "timestamp": ts,
        "uv": {
            "latest_uv_island_wide": current_uv,
            "timestamp": uv_ts,
            "note": "UV endpoint is island-wide (not region-specific)."
        },
        "pm25": {
            "avg_across_regions": avg_pm25,
            "timestamp": pm25_ts,
            "by_region": pm25_df.to_dict(orient="records") if not pm25_df.empty else []
        },
        "psi": {
            "avg_across_regions": avg_psi,
            "timestamp": psi_ts,
            "by_region": psi_df.to_dict(orient="records") if not psi_df.empty else []
        },
        "avoid_outdoors_regions": regions_avoid,
        "uv_warning": uv_warning,
        "station_sample": merged_rows
    }


# =========================================================
# COLAB-STYLE FORMATTER FOR /log
# =========================================================
def format_like_colab(snapshot: dict) -> str:
    ts = snapshot.get("timestamp")
    uv = snapshot.get("uv", {}).get("latest_uv_island_wide", 0)
    pm25_avg = snapshot.get("pm25", {}).get("avg_across_regions", 0)
    psi_avg = snapshot.get("psi", {}).get("avg_across_regions", 0)

    station_sample = snapshot.get("station_sample", [])
    if station_sample:
        avg_temp = sum(r["air_temperature"] for r in station_sample) / len(station_sample)
        avg_humid = sum(r["relative_humidity"] for r in station_sample) / len(station_sample)
        avg_wind = sum(r["wind_speed"] for r in station_sample) / len(station_sample)
        avg_wind_dir = sum(r["wind_direction"] for r in station_sample) / len(station_sample)
        avg_rain = sum(r["rainfall"] for r in station_sample) / len(station_sample)
    else:
        avg_temp = avg_humid = avg_wind = avg_wind_dir = avg_rain = 0

    lines = []
    lines.append(f"✅ Data Synchronized for {ts}")
    lines.append(f"☀️ UV Index (latest hour, island-wide): {uv:.1f}")
    lines.append(f"🫁 PM2.5 (1h) avg across regions: {pm25_avg:.1f}")
    lines.append(f"🫁 PSI (24h) avg across regions: {psi_avg:.1f}")
    lines.append("")
    lines.append("✅ Summary")
    lines.append(
        f"{avg_temp:.1f}°C | {avg_humid:.1f}% Humid | {avg_wind:.1f}m/s Wind @ {avg_wind_dir:.0f}° | "
        f"Rain: {avg_rain:.1f}mm | PM2.5: {pm25_avg:.1f} | PSI: {psi_avg:.1f} | UV: {uv:.1f}"
    )
    lines.append("")
    lines.append("--- [AI STATUS LOG] ---")

    if 0 <= avg_wind_dir <= 90:
        lines.append(f"🤖 [ANALYSIS]: NE Winds ({avg_wind_dir:.0f}°). Likely bringing cleaner air mass.")
    elif 180 <= avg_wind_dir <= 240 and pm25_avg > 30:
        lines.append(f"🤖 [PREDICTION]: SW Winds ({avg_wind_dir:.0f}°). Risk of regional haze transport INCREASED.")

    lines.append("🤖 [STATUS]: Environment stable.")
    if pm25_avg <= 55 and uv < 8 and avg_temp <= 30:
        lines.append("🤖 [STATUS]: Environment stable. No immediate intervention required.")

    lines.append("")
    lines.append("--- [REGIONAL OUTDOOR GUIDANCE] ---")

    pm25_by_region = snapshot.get("pm25", {}).get("by_region", [])
    psi_by_region = snapshot.get("psi", {}).get("by_region", [])

    if pm25_by_region:
        worst_pm25 = max(pm25_by_region, key=lambda x: float(x["pm25"]))
        lines.append(f"🫁 PM2.5 (1h) worst region: {worst_pm25['region'].upper()} ({float(worst_pm25['pm25']):.1f})")
        elevated = [r for r in pm25_by_region if float(r["pm25"]) > 55]
        if not elevated:
            lines.append("✅ [PM2.5]: No regions above the elevated threshold right now.")
        else:
            lines.append("🚨 [PM2.5 ALERT]: Elevated PM2.5 detected in these regions:")
            for r in sorted(elevated, key=lambda x: float(x["pm25"]), reverse=True):
                lines.append(f"   - {r['region'].upper()}: {float(r['pm25']):.1f}")
    else:
        lines.append("⚠️ [PM2.5]: Region data unavailable.")

    if psi_by_region:
        worst_psi = max(psi_by_region, key=lambda x: float(x["psi"]))
        lines.append("")
        lines.append(f"🫁 PSI (24h) worst region: {worst_psi['region'].upper()} ({float(worst_psi['psi']):.1f})")

        moderate = [r for r in psi_by_region if 51 <= float(r["psi"]) < 101]
        unhealthy = [r for r in psi_by_region if float(r["psi"]) >= 101]

        if unhealthy:
            lines.append("🚨 [PSI ALERT]: Unhealthy PSI in these regions:")
            for r in sorted(unhealthy, key=lambda x: float(x["psi"]), reverse=True):
                lines.append(f"   - {r['region'].upper()}: {float(r['psi']):.1f}")
        elif moderate:
            lines.append("🟡 [PSI]: Moderate PSI in these regions (sensitive groups take caution):")
            for r in sorted(moderate, key=lambda x: float(x["psi"]), reverse=True):
                lines.append(
                    f"   - {r['region'].upper()}: {float(r['psi']):.1f} → Reduce prolonged outdoor activity if symptomatic/sensitive."
                )
        else:
            lines.append("✅ [PSI]: All regions are in the 'Good' range right now.")
    else:
        lines.append("⚠️ [PSI]: Region data unavailable.")

    return "\n".join(lines)
