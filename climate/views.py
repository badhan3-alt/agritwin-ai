from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.utils.translation import gettext as _
from farms.services import owned_farm, analysis_context
from .services import NASADataUnavailable

def unavailable(request, farm, error, active_page="climate"):
    response = render(request, "climate/unavailable.html", {"farm": farm, "climate_error": str(error), "active_page": active_page}, status=503)
    response["Retry-After"] = "30"
    response["Cache-Control"] = "private, no-store"
    return response

@require_GET
def dashboard(request, pk):
    farm = owned_farm(request, pk)
    try:
        context = analysis_context(farm)
    except NASADataUnavailable as error:
        return unavailable(request, farm, error)
    return render(request, "climate/dashboard.html", {**context, "active_page": "climate"})

@require_POST
def refresh(request, pk):
    farm = owned_farm(request, pk)
    try:
        analysis_context(farm, refresh=True)
    except NASADataUnavailable as error:
        messages.error(request, _("NASA data could not be refreshed. %(error)s If a valid NASA analysis was saved before, it is retained with its original retrieval time.") % {"error": _(str(error))})
    else:
        messages.success(request, _("NASA POWER data refreshed. Rotation scores were recalculated from the same NASA observations."))
    return redirect("climate:dashboard", pk=farm.pk)

@require_GET
def nasa_source(request, pk):
    farm = owned_farm(request, pk)
    try:
        context = analysis_context(farm)
    except NASADataUnavailable as error:
        return JsonResponse({"error": _(str(error))}, status=503, headers={"Retry-After": "30", "Cache-Control": "private, no-store"})
    response = JsonResponse(context["climate"]["raw_response"], json_dumps_params={"indent": 2})
    response["Content-Disposition"] = f'attachment; filename="nasa-power-farm-{farm.pk}.json"'
    response["Cache-Control"] = "private, no-store"
    return response
