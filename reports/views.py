import csv
import io
import json
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import get_language, gettext as _
from core.localization import localize_text, localize_value
from farms.services import analysis_context, owned_farm
from climate.services import NASADataUnavailable
from climate.views import unavailable

DISCLAIMER = "Prototype screening only. Scores are relative comparisons, not success probabilities, yield predictions, or financial forecasts. Confirm crop calendars, soil tests, drainage, irrigation and markets with a local agricultural advisor."

def detail(request, pk):
    farm = owned_farm(request, pk)
    try:
        context = analysis_context(farm)
    except NASADataUnavailable as error:
        return unavailable(request, farm, error, "reports")
    return render(request, "reports/detail.html", {**context, "generated_at": timezone.now(), "active_page": "reports", "report_disclaimer": DISCLAIMER})

def safe_cell(value):
    text = str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else text

def download(request, pk, format):
    if format not in {"json", "csv", "pdf"}:
        raise Http404("Unsupported report format")
    farm = owned_farm(request, pk)
    if format == "pdf":
        from .pdf import build_pdf_report
        response = HttpResponse(build_pdf_report(farm), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="agritwin-farm-{farm.pk}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
    try:
        context = analysis_context(farm)
    except NASADataUnavailable as error:
        return unavailable(request, farm, error, "reports")
    generated = timezone.now().isoformat()
    if format == "json":
        payload = {"project": "AgriTwin AI", "language": get_language(), "generated_at": generated, "analyzed_at": context["analysis"].analyzed_at.isoformat(), "farm": farm.to_profile(), "climate": context["climate"], "strategies": context["strategies"], "disclaimer": _(DISCLAIMER)}
        if (get_language() or "").startswith("bn"):
            payload["display_strategies"] = localize_value(context["strategies"])
        response = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2), content_type="application/json; charset=utf-8")
    else:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow([_("AgriTwin AI farm report"), safe_cell(farm.name)])
        writer.writerow([_("Generated"), generated])
        writer.writerow([_("Location"), safe_cell(localize_text(farm.location_name))])
        writer.writerow([_("Latitude"), farm.latitude])
        writer.writerow([_("Longitude"), farm.longitude])
        writer.writerow([_("Farm area (acres)"), farm.farm_size_acres])
        writer.writerow([_("Current rotation"), safe_cell(farm.crop_names)])
        writer.writerow([_("Soil texture"), farm.get_soil_type_display()])
        writer.writerow([_("Soil pH"), farm.soil_ph if farm.soil_ph is not None else _("Unknown; requires a soil test")])
        writer.writerow([_("Drainage"), farm.get_drainage_display()])
        writer.writerow([_("Irrigation"), farm.get_irrigation_availability_display()])
        writer.writerow([_("Priority"), farm.get_farming_priority_display()])
        writer.writerow([_("Budget"), farm.get_budget_display()])
        writer.writerow([_("Analyzed"), context["analysis"].analyzed_at.isoformat()])
        writer.writerow([_("Data mode"), _("NASA data")])
        writer.writerow([_("Source"), safe_cell(localize_text(context["climate"]["source"]))])
        writer.writerow([_("NASA request URL"), safe_cell(context["climate"]["provenance"]["url"])])
        writer.writerow([_("NASA retrieved at"), safe_cell(context["climate"]["provenance"]["retrieved_at"])])
        writer.writerow([_("Data period"), safe_cell(localize_text(context["climate"]["provenance"].get("period", "Not available")))])
        writer.writerow([_("Source limitations"), safe_cell(localize_text(context["climate"]["provenance"].get("disclaimer", "")))])
        writer.writerow([_("Disclaimer"), _(DISCLAIMER)])
        writer.writerow([])
        writer.writerow([_("Strategy"), _("Crop sequence"), _("Eligible"), _("Relative score /100"), _("Water"), _("Climate"), _("Soil"), _("Economic"), _("Illustrative water demand mm"), _("Calendar"), _("Risks and uncertainties")])
        for strategy in context["strategies"]:
            components = strategy["components"]
            row = [localize_text(strategy["name"]), " -> ".join(localize_text(c["name"]) for c in strategy["sequence"]), _("Yes") if strategy.get("is_eligible", False) else _("No"), strategy["composite_score"], components["water"], components["climate"], components["soil"], components["economic"], strategy["water_demand_mm"], localize_text(strategy["calendar"]["description"]), "; ".join(localize_text(item) for item in strategy["risks"] + strategy["uncertainties"])]
            writer.writerow([safe_cell(value) for value in row])
        response = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="agritwin-farm-{farm.pk}.{format}"'
    response["Cache-Control"] = "private, no-store"
    return response
