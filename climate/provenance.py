"""Identify a stored NASA response before it can drive advice or exports."""
from urllib.parse import urlparse

def is_nasa_climate(climate):
    if not isinstance(climate, dict) or climate.get("status") != "live":
        return False
    provenance = climate.get("provenance")
    raw = climate.get("raw_response")
    if not isinstance(provenance, dict) or not isinstance(raw, dict):
        return False
    url = provenance.get("url")
    properties = raw.get("properties")
    if not isinstance(url, str) or not isinstance(properties, dict):
        return False
    try:
        source = urlparse(url)
    except ValueError:
        return False
    parameters = properties.get("parameter", {})
    return (
        source.scheme == "https" and source.netloc == "power.larc.nasa.gov"
        and source.path.rstrip("/") == "/api/temporal/climatology/point"
        and isinstance(parameters, dict)
        and all(name in parameters for name in ("T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"))
        and isinstance(climate.get("monthly_data"), list)
        and len(climate["monthly_data"]) == 12
        and bool(provenance.get("retrieved_at"))
    )
