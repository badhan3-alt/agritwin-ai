"""Offline Bangladesh district presets shared by forms and map data."""
import json
from pathlib import Path
from django.utils.translation import get_language, gettext as _

with (Path(__file__).parent / "data" / "bangladesh_regions.json").open(encoding="utf-8") as stream:
    _catalog = json.load(stream)

REGIONS = _catalog["regions"]
REGIONS_BY_ID = {region["id"]: region for region in REGIONS}
REGION_ALIASES = {
    "jessore": "jashore", "chittagong": "chattogram", "comilla": "cumilla",
    "barisal": "barishal", "bogra": "bogura", "coxsbazar": "coxs_bazar",
    "jhalakathi": "jhalokathi",
}

def canonical_region_id(value):
    return REGION_ALIASES.get(value, value)

def district_choices():
    """Native select optgroups keep all 64 districts usable without JavaScript."""
    choices = [("", _("Choose a district or set coordinates"))]
    bangla = (get_language() or "").startswith("bn")
    for division in sorted({region["division"] for region in REGIONS}):
        districts = [region for region in REGIONS if region["division"] == division]
        label = f"{districts[0]['division_bn']} বিভাগ" if bangla else f"{division} Division"
        choices.append((label, [(region["id"], region["district_bn"] if bangla else region["district"]) for region in districts]))
    return choices
