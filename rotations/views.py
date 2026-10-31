from django.shortcuts import render
from farms.services import analysis_context, owned_farm
from climate.services import NASADataUnavailable
from climate.views import unavailable

def explorer(request, pk):
    farm = owned_farm(request, pk)
    try:
        context = analysis_context(farm)
    except NASADataUnavailable as error:
        return unavailable(request, farm, error, "rotations")
    return render(request, "rotations/explorer.html", {**context, "active_page": "rotations"})
