from farms.models import Farm
from django.conf import settings
from django.utils.translation import gettext as _

def navigation(request):
    language = getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)
    owned = Farm.objects.filter(owner_session=request.session.session_key) if request.session.session_key else Farm.objects.none()
    current = owned.filter(pk=request.session.get("current_farm_id")).first()
    ui = {"home": _("Overview"), "farms": _("My farms"), "setup": _("Farm setup"), "climate": _("Climate insights"), "rotations": _("Crop rotations"), "simulator": _("Digital twin"), "reports": _("Farm report"), "about": _("The science"), "new_farm": _("Add a farm"), "explore_demo": _("Explore NASA example farm")}
    js_translations = {
        "working": _("Working…"),
        "basemap_unavailable": _("The basemap is unavailable right now."),
        "basemap_help": _("Choose a region above or enter latitude and longitude. You can save and analyze your farm without the map."),
        "coordinates_help": _("Your coordinates are preserved. Choose a region or enter coordinates to continue."),
        "chart_label": _("Monthly precipitation bars and mean temperature line. The full values appear in the data table below."),
        "chart_title": _("Monthly rainfall and mean temperature"),
        "rainfall": _("precipitation"), "temperature": _("mean temperature"),
        "rain_unit": _("mm"), "temp_unit": _("°C"),
        "months": {"JAN": _("Jan"), "FEB": _("Feb"), "MAR": _("Mar"), "APR": _("Apr"), "MAY": _("May"), "JUN": _("Jun"), "JUL": _("Jul"), "AUG": _("Aug"), "SEP": _("Sep"), "OCT": _("Oct"), "NOV": _("Nov"), "DEC": _("Dec")},
        "month_names": {"JAN": _("January"), "FEB": _("February"), "MAR": _("March"), "APR": _("April"), "MAY": _("May"), "JUN": _("June"), "JUL": _("July"), "AUG": _("August"), "SEP": _("September"), "OCT": _("October"), "NOV": _("November"), "DEC": _("December")},
    }
    return {"farm": None, "selected_farm": None, "current_farm": current, "farms_count": owned.count(), "language": language, "ui": ui, "js_translations": js_translations}
