"""Minimized, session-checked context for a farmer's explicit opt-in."""
from climate.provenance import is_nasa_climate
from farms.models import Analysis
from farms.regions import REGIONS
from core.localization import localize_text, localize_value
from django.utils.translation import gettext as _

def farm_context(farm):
    # Do not send names, exact coordinates, session identifiers, budgets,
    # raw NASA responses, or API request URLs to an external AI provider.
    region = next((item for item in REGIONS if item["name"] == farm.location_name or f"{item['district']}, Bangladesh" == farm.location_name), None)
    place = localize_text(f"{region['district']}, {region['division']} Division, Bangladesh") if region else _("Bangladesh")
    result = {"farm": {"location_name": place, "crops": farm.crop_names.split(" → "), "soil_type": farm.get_soil_type_display(), "soil_ph": farm.soil_ph, "irrigation": farm.get_irrigation_availability_display(), "priority": farm.get_farming_priority_display(), "area": farm.farm_size_acres}, "climate": None, "strategies": []}
    analysis = Analysis.objects.filter(farm=farm).first()
    if analysis and is_nasa_climate(analysis.climate):
        provenance = analysis.climate["provenance"]
        result["climate"] = {"status": "live", "annual_summary": localize_value(analysis.climate["annual_summary"]), "provenance": {"period": localize_text(provenance["period"]), "retrieved_at": provenance["retrieved_at"], "url": "https://power.larc.nasa.gov/docs/services/api/temporal/climatology/"}}
        result["strategies"] = localize_value([{key: strategy[key] for key in ("name", "composite_score", "is_eligible", "description", "risks", "uncertainties")} for strategy in analysis.strategies])
    return result
