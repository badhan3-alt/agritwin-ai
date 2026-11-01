from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST, require_http_methods
from django.utils.translation import gettext as _
from climate.services import NASADataUnavailable
from .forms import FarmForm, REGIONS
from .models import Farm
from .services import analysis_context, ensure_analysis, owned_farm, owned_farms, session_key

def farm_list(request):
    farms = owned_farms(request)
    return render(request, "farms/list.html", {"farms": farms, "active_page": "farms"})

@require_http_methods(["GET", "POST"])
def create(request):
    form = FarmForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        farm = form.save(commit=False)
        if request.user.is_authenticated:
            farm.owner = request.user
            farm.owner_session = ""
        else:
            farm.owner_session = session_key(request)
        farm.save()
        request.session["current_farm_id"] = farm.pk
        try:
            ensure_analysis(farm)
        except NASADataUnavailable:
            messages.warning(request, _("Your farm is saved. NASA POWER is unavailable, so climate analysis and crop scores will be available after a successful NASA request."))
        else:
            messages.success(request, _("Your farm is ready. Its climate analysis and crop comparison use NASA POWER data."))
        return redirect("farms:detail", pk=farm.pk)
    return render(request, "farms/form.html", {"form": form, "regions": REGIONS, "active_page": "setup"})

def detail(request, pk):
    farm = owned_farm(request, pk)
    from notebook.services import farm_record_summary
    try:
        context = analysis_context(farm)
    except NASADataUnavailable as error:
        context = {"farm": farm, "analysis": None, "climate": None, "strategies": [], "recommended": None, "climate_error": str(error)}
    return render(request, "farms/detail.html", {**context, "records": farm_record_summary(farm), "active_page": "farms"})

@require_http_methods(["GET", "POST"])
def edit(request, pk):
    farm = owned_farm(request, pk)
    form = FarmForm(request.POST if request.method == "POST" else None, instance=farm)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            farm = form.save()
            if hasattr(farm, "analysis"):
                farm.analysis.delete()
        try:
            ensure_analysis(farm)
        except NASADataUnavailable:
            messages.warning(request, _("Farm updated. NASA POWER is unavailable; retry the NASA connection to calculate an analysis for these new inputs."))
        else:
            messages.success(request, _("Farm updated. Climate analysis and rotation scores were recalculated using NASA POWER data."))
        return redirect("farms:detail", pk=farm.pk)
    return render(request, "farms/form.html", {"farm": farm, "form": form, "regions": REGIONS, "active_page": "setup"})

@require_POST
def delete(request, pk):
    farm = owned_farm(request, pk, select=False)
    farm.delete()
    if request.session.get("current_farm_id") == pk:
        request.session.pop("current_farm_id", None)
    messages.success(request, _("Farm and all its saved records and photos deleted."))
    return redirect("farms:list")
