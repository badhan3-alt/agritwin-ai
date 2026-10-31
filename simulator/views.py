from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from farms.services import analysis_context, owned_farm
from climate.services import NASADataUnavailable
from climate.views import unavailable
from .forms import ScenarioForm
from . import services

@require_http_methods(["GET", "POST"])
def workbench(request, pk):
    farm = owned_farm(request, pk)
    try:
        context = analysis_context(farm)
    except NASADataUnavailable as error:
        return unavailable(request, farm, error, "simulator")
    form = ScenarioForm(request.POST if request.method == "POST" else None, initial={"irrigation": farm.irrigation_availability, "priority": farm.farming_priority})
    result = None
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        result = services.simulate(farm.to_profile(), context["climate"], data["rainfall_delta_pct"], data["temp_delta_c"], data["irrigation"], data["priority"])
    context.update({"active_page": "simulator", "form": form, "result": result, "baseline_strategies": context["strategies"]})
    return render(request, "simulator/workbench.html", context)
