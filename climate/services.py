"""NASA POWER climatology with explicit provenance and no synthetic fallback.

Monthly rain totals are converted using NASA's response unit metadata. Every
runtime baseline is a validated NASA response or an unchanged cached copy.
"""
from copy import deepcopy
from datetime import datetime, timezone
import logging
import math

import requests
from django.core.cache import cache
from .provenance import is_nasa_climate

logger = logging.getLogger(__name__)
POWER_URL = "https://power.larc.nasa.gov/api/temporal/climatology/point"
POWER_DOCS = "https://power.larc.nasa.gov/docs/services/api/temporal/climatology/"
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
DAYS = [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
RABI = {"NOV", "DEC", "JAN", "FEB", "MAR"}


class NASADataUnavailable(RuntimeError):
    """A valid NASA baseline is required, but none could be obtained."""


UNAVAILABLE_MESSAGE = (
    "NASA POWER data could not be retrieved or validated for this location. "
    "No sample data has been substituted. Your farm details are saved; retry the NASA request shortly."
)


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _number(value, fill=-999.0):
    number = float(value)
    if not math.isfinite(number) or number == fill:
        raise ValueError("POWER returned a missing or non-finite required observation.")
    return number


def _summarize(monthly):
    rabi = [row for row in monthly if row["month_code"] in RABI]
    rabi_rain = sum(row["precip_mm"] for row in rabi)
    wetness = [row["soil_wetness_root"] for row in rabi if row["soil_wetness_root"] is not None]
    if rabi_rain < 50:
        severity, index = "Very low dry-season rainfall; review irrigation capacity", 85
    elif rabi_rain < 100:
        severity, index = "Low dry-season rainfall; supplemental water may be needed", 55
    else:
        severity, index = "Review rainfall timing alongside crop water demand", 25
    return {
        "total_precip_mm": round(sum(row["precip_mm"] for row in monthly), 1),
        "rabi_dry_season_precip_mm": round(rabi_rain, 1),
        "kharif1_premonsoon_precip_mm": round(sum(row["precip_mm"] for row in monthly if row["month_code"] in {"APR", "MAY", "JUN"}), 1),
        "kharif2_monsoon_precip_mm": round(sum(row["precip_mm"] for row in monthly if row["month_code"] in {"JUL", "AUG", "SEP", "OCT"}), 1),
        "avg_annual_temp_c": round(sum(row["temp_mean_c"] * days for row, days in zip(monthly, DAYS)) / sum(DAYS), 2),
        "heat_stress_months": [row["month_name"] for row in monthly if row["temp_max_c"] >= 34],
        "rabi_soil_wetness_avg": round(sum(wetness) / len(wetness), 3) if wetness else None,
        "dry_season_severity": severity,
        "water_stress_index": index,
        "heat_indicator_description": "Months with climatological maximum temperature at or above 34°C. This is screening, not heatwave frequency or crop-stage damage prediction.",
    }


def _parse_power(payload, latitude, longitude, request_url):
    params = payload["properties"]["parameter"]
    metadata = payload.get("parameters", {})
    header = payload.get("header", {})
    fill = float(header.get("fill_value", -999))
    precip_unit = metadata.get("PRECTOTCORR", {}).get("units", "").strip().lower().replace(" ", "")
    if precip_unit not in {"mm/day", "mm/d", "mm"}:
        raise ValueError("Unsupported or missing POWER precipitation unit metadata.")
    for parameter in ("T2M", "T2M_MAX", "T2M_MIN"):
        if metadata.get(parameter, {}).get("units", "").strip().lower() not in {"c", "°c", "degc"}:
            raise ValueError("Unsupported or missing POWER temperature unit metadata.")
    monthly = []
    for i, code in enumerate(MONTHS):
        rain = _number(params["PRECTOTCORR"][code], fill)
        if rain < 0:
            raise ValueError("POWER returned negative precipitation.")
        if precip_unit in {"mm/day", "mm/d"}:
            rain *= DAYS[i]
        temperatures = [_number(params[key][code], fill) for key in ("T2M", "T2M_MAX", "T2M_MIN")]
        if not (-100 <= temperatures[2] <= temperatures[0] <= temperatures[1] <= 80):
            raise ValueError("POWER returned inconsistent temperature observations.")
        try:
            wet = _number(params.get("GWETROOT", {}).get(code), fill)
            wet = wet if 0 <= wet <= 1 else None
        except (ValueError, TypeError):
            wet = None
        monthly.append({"month_code": code, "month_name": MONTH_NAMES[i],
            "temp_mean_c": round(temperatures[0], 2), "temp_max_c": round(temperatures[1], 2),
            "temp_min_c": round(temperatures[2], 2), "precip_mm": round(rain, 1),
            "soil_wetness_root": wet})
    summary = _summarize(monthly)
    return {
        "status": "live", "source": "NASA POWER climatology API",
        "location": {"lat": float(latitude), "lon": float(longitude)},
        "raw_response": deepcopy(payload),
        "provenance": {
            "provider": "NASA Langley Research Center POWER Project / MERRA-2 reanalysis",
            "period": header.get("range", "Climatological period not supplied by API"),
            "resolution": "Regional MERRA-2 meteorology, native grid approximately 0.5° × 0.625°",
            "disclaimer": "Regional climatological screening, not a field measurement, seasonal forecast, or soil test. Temperature maxima describe climatological extremes, not heatwave counts.",
            "retrieved_at": _timestamp(), "url": request_url,
            "documentation_url": POWER_DOCS,
            "request_parameters": {"latitude": round(float(latitude), 4), "longitude": round(float(longitude), 4),
                "parameters": "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,GWETROOT", "community": "AG", "format": "JSON"},
            "rainfall_conversion": f"POWER PRECTOTCORR ({precip_unit}) converted to monthly mm using average month length; February is 28.25 days." if precip_unit != "mm" else "POWER metadata reports monthly precipitation in mm; no daily conversion applied.",
            "parameter_units": {key: value.get("units") for key, value in metadata.items()},
        },
        "monthly_data": monthly, "annual_summary": summary,
        "soil_moisture": {"status": "available" if summary["rabi_soil_wetness_avg"] is not None else "unavailable",
            "relative_wetness": summary["rabi_soil_wetness_avg"],
            "description": "POWER GWETROOT: dimensionless regional root-zone relative wetness from reanalysis (0–1), averaged across November–March. This is not volumetric soil moisture and is not a SMAP retrieval. Field drainage, pH and nutrients require local assessment."},
    }


def get_climate(latitude, longitude, *, refresh=False):
    """Return NASA data or raise; never replace missing observations with samples."""
    latitude, longitude = float(latitude), float(longitude)
    if not (math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Coordinates must be finite and within latitude/longitude bounds.")
    key = f"agritwin:power:v3:{latitude:.4f}:{longitude:.4f}"
    if not refresh:
        cached = cache.get(key)
        if is_nasa_climate(cached):
            return deepcopy(cached)
        if isinstance(cached, dict) and cached.get("_nasa_unavailable"):
            raise NASADataUnavailable(UNAVAILABLE_MESSAGE)
    try:
        response = requests.get(POWER_URL, params={
            "parameters": "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,GWETROOT", "community": "AG",
            "latitude": round(latitude, 4), "longitude": round(longitude, 4), "format": "JSON",
        }, timeout=(4, 15), headers={"User-Agent": "AgriTwin-AI/2.0 (agricultural-climate-screening)"})
        response.raise_for_status()
        result = _parse_power(response.json(), latitude, longitude, response.url)
        if not is_nasa_climate(result):
            raise ValueError("NASA response does not contain a complete source-traceable baseline.")
        cache.set(key, result, 6 * 60 * 60)
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError) as error:
        logger.warning("NASA POWER request unavailable or invalid: %s", type(error).__name__)
        # A short failure marker prevents immediate duplicate requests from
        # multiple pages; it can never be returned as a climate observation.
        cache.set(key, {"_nasa_unavailable": True}, 30)
        raise NASADataUnavailable(UNAVAILABLE_MESSAGE) from error
    return deepcopy(result)


def apply_scenario(climate, rainfall_delta_pct, temp_delta_c):
    """Perturb one stored baseline; do not refetch or invent a soil-water model."""
    if not is_nasa_climate(climate):
        raise NASADataUnavailable("A valid NASA POWER baseline is required before running a scenario.")
    rain, temperature = float(rainfall_delta_pct), float(temp_delta_c)
    if not (math.isfinite(rain) and math.isfinite(temperature) and -50 <= rain <= 50 and -1 <= temperature <= 5):
        raise ValueError("Scenario bounds are -50 to +50% rain and -1 to +5°C temperature.")
    result = deepcopy(climate)
    for row in result["monthly_data"]:
        row["baseline_precip_mm"] = row["precip_mm"]
        row["precip_mm"] = round(row["precip_mm"] * (1 + rain / 100), 1)
        for field in ("temp_mean_c", "temp_max_c", "temp_min_c"):
            row[field] = round(row[field] + temperature, 2)
    result["annual_summary"] = _summarize(result["monthly_data"])
    result["scenario"] = {"rainfall_delta_pct": rain, "temp_delta_c": temperature,
        "disclaimer": "Sensitivity test, not a climate forecast. Regional soil wetness is held at baseline; this prototype does not model soil-water dynamics."}
    return result
