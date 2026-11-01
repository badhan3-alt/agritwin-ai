from django.shortcuts import get_object_or_404
from climate import services as climate_services
from climate.provenance import is_nasa_climate
from rotations import services as rotation_services
from .models import Farm, Analysis

def session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key

def owned_farms(request):
    """Account ownership takes precedence; a session can only access guest farms."""
    if request.user.is_authenticated:
        return Farm.objects.filter(owner=request.user)
    if request.session.session_key:
        return Farm.objects.filter(owner__isnull=True, owner_session=request.session.session_key)
    return Farm.objects.none()


def owned_farm(request, pk, *, select=True):
    farm = get_object_or_404(owned_farms(request), pk=pk)
    if select:
        request.session["current_farm_id"] = farm.pk
    return farm

def ensure_analysis(farm, refresh=False):
    existing = Analysis.objects.filter(farm=farm).first()
    if existing and is_nasa_climate(existing.climate) and not refresh:
        return existing
    climate = climate_services.get_climate(farm.latitude, farm.longitude, refresh=refresh)
    if not is_nasa_climate(climate):
        raise climate_services.NASADataUnavailable("A validated NASA POWER response is required before analysis can run. Retry the NASA connection.")
    strategies = rotation_services.evaluate_rotations(farm.to_profile(), climate)
    analysis, _ = Analysis.objects.update_or_create(farm=farm, defaults={"climate": climate, "strategies": strategies})
    return analysis

def analysis_context(farm, refresh=False):
    analysis = ensure_analysis(farm, refresh=refresh)
    eligible = [s for s in analysis.strategies if s.get("is_eligible", s.get("calendar", {}).get("is_feasible", False))]
    return {"farm": farm, "analysis": analysis, "climate": analysis.climate, "strategies": analysis.strategies, "recommended": eligible[0] if eligible else None}
