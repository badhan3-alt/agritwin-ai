from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from climate.services import NASADataUnavailable
from farms.models import Farm
from farms.services import ensure_analysis, session_key
from .error_views import csrf_failure  # Keep the previous import path usable.

def home(request):
    return render(request, "core/home.html", {"active_page": "home"})

def about(request):
    return render(request, "core/about.html", {"active_page": "about"})

@require_GET
def health(request):
    return JsonResponse({"status": "ok", "application": "AgriTwin AI", "framework": "Django", "version": "2.0.0"})

@require_POST
def language(request):
    chosen = request.POST.get("language", "bn")
    if chosen in {"en", "bn"}:
        request.session["language"] = chosen
    target = request.POST.get("next", reverse("core:home"))
    if not url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        target = reverse("core:home")
    return redirect(target)

@require_POST
def demo(request):
    owner = session_key(request)
    farm = Farm.objects.filter(owner_session=owner, name="Rajshahi example farm").first()
    if farm is None:
        farm = Farm.objects.create(owner_session=owner, **Farm.example_defaults())
    request.session["current_farm_id"] = farm.pk
    try:
        ensure_analysis(farm)
    except NASADataUnavailable:
        messages.warning(request, _("The example farm is saved. NASA POWER could not be reached; retry its climate analysis when connectivity returns."))
    else:
        messages.info(request, _("This example combines an illustrative farm profile with actual NASA POWER climate data for Rajshahi."))
    return redirect("farms:detail", pk=farm.pk)
