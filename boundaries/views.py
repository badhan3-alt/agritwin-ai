from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from farms.services import owned_farm
from .forms import BoundaryForm
from .models import FarmBoundary


@require_http_methods(["GET", "POST"])
def editor(request, pk):
    farm = owned_farm(request, pk)
    boundary = FarmBoundary.objects.filter(farm=farm).first()
    form = BoundaryForm(request.POST if request.method == "POST" else None, instance=boundary)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            boundary = form.save(commit=False)
            boundary.farm = farm
            boundary.save()
            if form.cleaned_data["use_estimated_area"]:
                farm.farm_size_acres = round(boundary.area_acres, 4)
                farm.save(update_fields=["farm_size_acres", "updated_at"])
        messages.success(request, _("Farm boundary saved. Its area is an estimate, not a land survey."))
        return redirect("boundaries:editor", pk=pk)
    if boundary and request.method == "POST":
        # ModelForm may assign valid new geometry before another field fails;
        # the saved preview should continue showing the persisted boundary.
        boundary.refresh_from_db()
    response = render(request, "boundaries/editor.html", {"farm": farm, "boundary": boundary, "form": form, "active_page": "boundary"})
    response["Cache-Control"] = "private, no-store"
    return response


@require_POST
def delete(request, pk):
    farm = owned_farm(request, pk)
    FarmBoundary.objects.filter(farm=farm).delete()
    messages.success(request, _("Boundary removed. Your saved farm size is unchanged."))
    return redirect("boundaries:editor", pk=pk)


@require_GET
def download(request, pk):
    farm = owned_farm(request, pk)
    boundary = get_object_or_404(FarmBoundary, farm=farm)
    response = JsonResponse({"type": "Feature", "properties": {"farm": farm.name, "estimated_area_acres": boundary.area_acres}, "geometry": boundary.geometry})
    response["Content-Disposition"] = f'attachment; filename="agritwin-boundary-{farm.pk}.geojson"'
    response["Cache-Control"] = "private, no-store"
    return response
