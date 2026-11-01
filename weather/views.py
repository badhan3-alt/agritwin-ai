from copy import deepcopy

from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from farms.services import owned_farm
from .services import WeatherUnavailable, condition_label, get_weather


def _dashboard(request, pk, *, refresh=False):
    farm = owned_farm(request, pk)
    context = {"farm": farm, "active_page": "weather", "forecast": None, "weather_error": None}
    status = 200
    try:
        forecast = deepcopy(get_weather(farm.latitude, farm.longitude, refresh=refresh))
        forecast["current"]["condition"] = condition_label(forecast["current"]["weather_code"])
        for day in forecast["days"]:
            day["condition"] = condition_label(day["weather_code"])
        context["forecast"] = forecast
    except WeatherUnavailable as error:
        context["weather_error"] = str(error)
        status = 503
    return render(request, "weather/dashboard.html", context, status=status)


@require_GET
def dashboard(request, pk):
    return _dashboard(request, pk)


@require_POST
def refresh(request, pk):
    return _dashboard(request, pk, refresh=True)
