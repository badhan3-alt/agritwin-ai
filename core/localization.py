"""Translate generated advice at presentation time, preserving stored evidence.

Scientific services keep canonical English strings and numeric inputs in their
saved JSON. This module translates the known messages when shown to farmers;
it never rewrites NASA responses, identifiers, URLs, or arbitrary user names.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re

from django.utils.translation import get_language, gettext

_CROP_NAMES = {
    "T. Aman Rice": "T. Aman Rice", "T. Aman rice": "T. Aman Rice",
    "Aman Rice": "T. Aman Rice", "Aman rice": "T. Aman Rice",
    "Boro Rice": "Boro Rice", "Boro rice": "Boro Rice",
    "Lentil (Masur)": "Lentil (Masur)", "Lentil": "Lentil (Masur)",
    "Mustard (Sarisha)": "Mustard (Sarisha)", "Mustard": "Mustard (Sarisha)",
    "Mung Bean (Moog)": "Mung Bean (Moog)", "Mung bean": "Mung Bean (Moog)",
    "Winter Maize (Bhutta)": "Winter Maize (Bhutta)", "Maize": "Winter Maize (Bhutta)",
    "Wheat (Gom)": "Wheat (Gom)", "Wheat": "Wheat (Gom)",
}
_MONTHS = {
    "Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April",
    "May": "May", "Jun": "June", "Jul": "July", "Aug": "August",
    "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December",
}
_SOIL_WARNING = re.compile(r"(.+): entered soil texture is outside this prototype profile's preferred soils; verify drainage and suitability locally\.")
_PH_WARNING = re.compile(r"(.+): entered pH is outside the profile range ([\d.]+)[–-]([\d.]+)\.")
_SENSITIVITY = re.compile(r"([+-]?\d+(?:\.\d+)?) score points: (.+)\.")
_FACTOR = re.compile(r"(water|climate|soil|economic) ([+-]?\d+(?:\.\d+)?)")
_PERIOD = re.compile(r"(\d+)-year Meteorological and Solar Monthly & Annual Climatologies \(([A-Za-z]+) (\d{4}) - ([A-Za-z]+) (\d{4})\)")
_DAY_MONTH = re.compile(r"(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)")
_RAIN_CONVERSION = re.compile(r"POWER PRECTOTCORR \(([^)]+)\) converted to monthly mm using average month length; February is 28\.25 days\.")
_TOP_STRATEGY = re.compile(r"(.+) has the highest eligible relative score under these assumptions\.")


@lru_cache(maxsize=1)
def _district_names():
    data_path = Path(__file__).resolve().parent.parent / "farms" / "data" / "bangladesh_regions.json"
    with data_path.open(encoding="utf-8") as stream:
        districts = json.load(stream)["regions"]
    translated = {region["name"]: f"{region['district_bn']}, {region['division_bn']} বিভাগ, বাংলাদেশ" for region in districts}
    for region in districts:
        translated[f"{region['district']}, Bangladesh"] = f"{region['district_bn']}, বাংলাদেশ"
    return translated


def _format(msgid, **values):
    return gettext(msgid) % values


def _sensitivity_explanation(value):
    factors = []
    for factor in value.split("; "):
        match = _FACTOR.fullmatch(factor)
        if match:
            factors.append(_format("%(component)s %(change)s", component=gettext(match[1]), change=match[2]))
        else:
            factors.append(gettext(factor))
    return "; ".join(factors)


def localize_text(value):
    """Translate a known generated sentence, leaving unknown/free text intact."""
    if not isinstance(value, str) or not (get_language() or "").startswith("bn"):
        return value
    if value in _CROP_NAMES:
        return gettext(_CROP_NAMES[value])
    if value in _district_names():
        return _district_names()[value]
    translated = gettext(value)
    if translated != value:
        return translated
    # A farm's crop_names value is generated from supported crop IDs, while
    # free-form names without a wholly known sequence remain unchanged.
    sequence = value.split(" → ")
    if len(sequence) > 1 and all(crop in _CROP_NAMES for crop in sequence):
        return " → ".join(gettext(_CROP_NAMES[crop]) for crop in sequence)
    match = _SOIL_WARNING.fullmatch(value)
    if match:
        return _format("%(crop)s: entered soil texture is outside this prototype profile's preferred soils; verify drainage and suitability locally.", crop=localize_text(match[1]))
    match = _PH_WARNING.fullmatch(value)
    if match:
        return _format("%(crop)s: entered pH is outside the profile range %(minimum)s–%(maximum)s.", crop=localize_text(match[1]), minimum=match[2], maximum=match[3])
    match = _SENSITIVITY.fullmatch(value)
    if match:
        return _format("%(delta)s score points: %(explanation)s.", delta=match[1], explanation=_sensitivity_explanation(match[2]))
    match = _DAY_MONTH.fullmatch(value)
    if match:
        return _format("%(day)s %(month)s", day=match[1], month=gettext(_MONTHS[match[2]]))
    match = _RAIN_CONVERSION.fullmatch(value)
    if match:
        return _format("POWER PRECTOTCORR (%(unit)s) converted to monthly mm using average month length; February is 28.25 days.", unit=match[1])
    match = _PERIOD.fullmatch(value)
    if match:
        return _format("%(years)s-year Meteorological and Solar Monthly & Annual Climatologies (%(start_month)s %(start_year)s - %(end_month)s %(end_year)s)", years=match[1], start_month=gettext(match[2]), start_year=match[3], end_month=gettext(match[4]), end_year=match[5])
    match = _TOP_STRATEGY.fullmatch(value)
    if match:
        return _format("%(strategy)s has the highest eligible relative score under these assumptions.", strategy=localize_text(match[1]))
    return value


_PRESERVE_KEYS = frozenset({
    "raw_response", "request_parameters", "parameter_units", "id", "crop_id",
    "type", "status", "season", "month_code", "url", "documentation_url",
    "planting_date", "harvest_date", "retrieved_at", "generated_at", "analyzed_at",
    "latitude", "longitude", "name_bn", "district_bn", "division_bn",
    "irrigation", "priority", "current_crops", "soil_type", "drainage",
    "irrigation_availability", "farming_priority", "budget",
})


def localize_value(value):
    """Return a localized presentation copy; retain raw NASA data and all IDs.

    Pass generated analysis/strategy dictionaries, never a user-entered farm
    profile: free-form profile fields should be rendered as the farmer wrote.
    """
    if isinstance(value, dict):
        return {key: deepcopy(item) if key in _PRESERVE_KEYS else localize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [localize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(localize_value(item) for item in value)
    return localize_text(value)
