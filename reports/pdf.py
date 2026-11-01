"""Private, offline PDF export of a farm and its saved evidence and records.

All free text is escaped before ReportLab sees its markup parser. Noto fonts
are bundled under the SIL OFL; HarfBuzz shapes Bangla words at layout time.
No maps, weather services, or NASA requests are made while exporting.
"""
from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import get_language, gettext as _
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import CondPageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

from boundaries.geometry import schematic_points
from climate.provenance import is_nasa_climate
from core.localization import localize_text
from farms.models import Analysis
from notebook.services import ledger_totals


FOREST = colors.HexColor("#173d32")
INK = colors.HexColor("#223d32")
MUTED = colors.HexColor("#526451")
QUIET = colors.HexColor("#f0f2e7")
BORDER = colors.HexColor("#d9e1d2")
PAGE_WIDTH, PAGE_HEIGHT = A4
CONTENT_WIDTH = PAGE_WIDTH - 96
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _fonts():
    font_dir = Path(settings.BASE_DIR) / "static" / "fonts"
    # These current Noto Bengali faces also contain the full Latin alphabet.
    # A single face per run avoids ReportLab's mixed-font word-shaping defect.
    for name, filename in (("AgriSans", "NotoSansBengali-Regular.ttf"), ("AgriSansBold", "NotoSansBengali-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(font_dir / filename), shapable=True))


def _markup(value):
    value = _CONTROL.sub("", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    value = value.translate({0x2192: " -> ", 0x2011: "-", 0x2013: "-", 0x2014: "-"})
    return escape(value).replace("\n", "<br/>")


def _digits(value):
    text = str(value)
    return text.translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")) if (get_language() or "").startswith("bn") else text


def _number(value, decimals=2):
    return _digits(f"{value:,.{decimals}f}") if value is not None else _("Not recorded")


def _date(value):
    if isinstance(value, datetime):
        return _digits(date_format(timezone.localtime(value), "j F Y, H:i"))
    return _digits(date_format(value, "j F Y"))


def _styles():
    body = ParagraphStyle("body", fontName="AgriSans", fontSize=9.5, leading=16, textColor=INK, spaceAfter=7, shaping=True, splitLongWords=True)
    return {
        "body": body,
        "title": ParagraphStyle("title", parent=body, fontName="AgriSansBold", fontSize=22, leading=33, textColor=FOREST, spaceAfter=8),
        "section": ParagraphStyle("section", parent=body, fontName="AgriSansBold", fontSize=14, leading=23, textColor=FOREST, spaceBefore=18, spaceAfter=10, keepWithNext=True),
        "subheading": ParagraphStyle("subheading", parent=body, fontName="AgriSansBold", fontSize=10.5, leading=18, spaceBefore=10, keepWithNext=True),
        "small": ParagraphStyle("small", parent=body, fontSize=8, leading=13, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=body, fontSize=8, leading=14, spaceAfter=0),
        "header": ParagraphStyle("header", parent=body, fontName="AgriSansBold", fontSize=8, leading=14, spaceAfter=0),
    }


def _p(value, styles, kind="body"):
    return Paragraph(_markup(value), styles[kind])


def _table(headers, rows, widths, styles):
    data = [[_p(cell, styles, "header") for cell in headers]]
    data.extend([_p(cell, styles, "cell") for cell in row] for row in rows)
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1, splitInRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), QUIET),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, BORDER),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def boundary_drawing(geometry):
    """North-up projected outline. No external basemap or surveyed precision."""
    width, height = CONTENT_WIDTH, 180
    drawing = Drawing(width, height)
    drawing.add(Rect(0, 0, width, height, fillColor=QUIET, strokeColor=BORDER, strokeWidth=0.7))
    points = schematic_points(geometry, width=width, height=height, margin=28)
    drawing.add(Polygon([coordinate for x, y in points for coordinate in (x, height - y)], fillColor=colors.HexColor("#d6eaa2"), strokeColor=FOREST, strokeWidth=1.5))
    arrow_x = width - 20
    drawing.add(Line(arrow_x, height - 52, arrow_x, height - 22, strokeColor=FOREST, strokeWidth=1))
    drawing.add(Polygon([arrow_x, height - 17, arrow_x - 3, height - 25, arrow_x + 3, height - 25], fillColor=FOREST, strokeColor=FOREST))
    drawing.add(String(arrow_x - 3, height - 13, "N", fontName="AgriSans", fontSize=8, fillColor=FOREST))
    return drawing


def build_pdf_report(farm):
    """Return PDF bytes for the already-authorized farm in the active language."""
    _fonts()
    styles = _styles()
    generated_at = timezone.now()
    analysis = Analysis.objects.filter(farm=farm).first()
    if analysis and not is_nasa_climate(analysis.climate):
        analysis = None
    climate = analysis.climate if analysis else None
    story = [_p("AgriTwin AI", styles, "subheading"), _p(_("Farm report"), styles, "title"), _p(farm.name, styles, "title"), _p(localize_text(farm.location_name), styles), _p(_("Prepared") + ": " + _date(generated_at) + " · Asia/Dhaka", styles, "small")]

    def section(title):
        story.extend([CondPageBreak(80), _p(title, styles, "section")])

    def note(value):
        story.append(_p(value, styles, "small"))

    section(_("Farm profile"))
    rows = [
        (_("Location"), localize_text(farm.location_name)),
        (_("Coordinates"), _number(farm.latitude, 5) + ", " + _number(farm.longitude, 5)),
        (_("Farm area (acres)"), _number(farm.farm_size_acres)),
        (_("Current crops"), farm.crop_names),
        (_("Soil type"), farm.get_soil_type_display()),
        (_("Soil pH"), _number(farm.soil_ph)),
        (_("Drainage"), farm.get_drainage_display()),
        (_("Irrigation"), farm.get_irrigation_availability_display()),
        (_("Priority"), farm.get_farming_priority_display()),
        (_("Budget"), farm.get_budget_display()),
    ]
    story.append(_table([_("Field"), _("Saved value")], rows, [150, CONTENT_WIDTH - 150], styles))

    section(_("Farm boundary map"))
    boundary = getattr(farm, "boundary", None)
    if boundary:
        story.append(boundary_drawing(boundary.geometry))
        note(_("North-up boundary schematic. No basemap. The drawn outline and estimated area are not a land survey."))
        note(_("Estimated area (acres)") + ": " + _number(boundary.area_acres, 3) + " · " + _("Perimeter (m)") + ": " + _number(boundary.perimeter_metres, 1))
    else:
        story.append(_p(_("No farm boundary has been saved. Coordinates above identify the saved farm location."), styles))

    section(_("Saved climate analysis and crop comparison"))
    if climate:
        summary = climate["annual_summary"]
        story.append(_table([_("Climate indicator"), _("Saved baseline")], [
            (_("Annual precipitation"), _number(summary["total_precip_mm"], 0) + " " + _("mm")),
            (_("Mean temperature"), _number(summary["avg_annual_temp_c"], 1) + " °C"),
            (_("Dry-season rainfall"), _number(summary["rabi_dry_season_precip_mm"], 0) + " " + _("mm")),
        ], [260, CONTENT_WIDTH - 260], styles))
        story.append(_p(localize_text(summary.get("dry_season_severity", "")), styles))
        note(_("Historical NASA POWER climate averages are not current weather or a forecast."))
        story.append(_table([_("Strategy"), _("Crop sequence"), _("Relative score /100"), _("Eligible")], [
            (localize_text(strategy["name"]), " → ".join(localize_text(crop["name"]) for crop in strategy["sequence"]), _number(strategy["composite_score"], 1), _("Yes") if strategy.get("is_eligible") else _("No"))
            for strategy in analysis.strategies
        ], [130, CONTENT_WIDTH - 265, 75, 60], styles))
        for strategy in analysis.strategies:
            story.append(_p(localize_text(strategy["name"]), styles, "subheading"))
            story.append(_p(localize_text(strategy["calendar"]["description"]), styles))
            for item in strategy.get("blocked_reasons", []) + strategy.get("risks", []) + strategy.get("uncertainties", []):
                story.append(_p("- " + localize_text(item), styles, "small"))
        section(_("Source and retrieval time"))
        provenance = climate.get("provenance", {})
        for label, value in [(_("Source"), climate.get("source", "NASA POWER")), (_("Reference period"), provenance.get("period", "")), (_("Retrieved"), provenance.get("retrieved_at", "")), (_("Analyzed"), _date(analysis.analyzed_at)), (_("NASA request URL"), provenance.get("url", ""))]:
            story.append(_p(str(label) + ": " + localize_text(value), styles, "small"))
        note(localize_text(provenance.get("disclaimer", "")))
    else:
        story.append(_p(_("No validated NASA analysis is saved. Farm details and records are exported below; climate values and crop scores are unavailable."), styles))

    section(_("Crop calendar and reminders"))
    events = list(farm.calendar_events.all())
    statuses = {"completed": _("Completed"), "overdue": _("Overdue"), "today": _("Due today"), "upcoming": _("Upcoming")}
    if events:
        story.append(_table([_("Planned date"), _("Task and crop"), _("Activity"), _("Status")], [(_date(event.due_date), event.title + (" / " + event.crop if event.crop else ""), event.get_event_type_display(), statuses[event.status]) for event in events], [95, CONTENT_WIDTH - 260, 95, 70], styles))
        for event in events:
            story.append(_p(event.title, styles, "subheading"))
            note(_("Reminder lead time (days)") + ": " + _digits(event.reminder_days))
            if event.notes:
                story.append(_p(event.notes, styles))
    else:
        story.append(_p(_("No calendar events recorded."), styles))
    note(_("Reminders appear inside AgriTwin. This PDF is a snapshot and does not send notifications."))

    section(_("Actual income and expenses"))
    totals = ledger_totals(farm)
    story.append(_table([_("Income (BDT)"), _("Expenses (BDT)"), _("Net profit / loss (BDT)")], [[_number(totals["income"]), _number(totals["expenses"]), _number(totals["net"])]], [CONTENT_WIDTH / 3] * 3, styles))
    note(_("Totals use recorded transactions only. Missing costs or sales affect the result; these are not predicted earnings."))
    entries = list(farm.ledger_entries.all())
    if entries:
        story.append(_table([_("Date"), _("Record type"), _("Description"), _("Amount (BDT)")], [(_date(entry.date), entry.get_entry_type_display(), entry.title + (" / " + entry.category if entry.category else ""), _number(entry.amount)) for entry in entries], [95, 85, CONTENT_WIDTH - 270, 90], styles))
        for entry in entries:
            if entry.notes:
                story.append(_p(_date(entry.date) + " / " + entry.title, styles, "subheading"))
                story.append(_p(entry.notes, styles))
    else:
        story.append(_p(_("No income or expense records yet."), styles))

    section(_("Soil test history"))
    tests = list(farm.soil_tests.all())
    if tests:
        story.append(_table([_("Test date"), _("pH"), _("N (mg/kg)"), _("P (mg/kg)"), _("K (mg/kg)")], [(_date(test.tested_on), _number(test.ph), _number(test.nitrogen), _number(test.phosphorus), _number(test.potassium)) for test in tests], [115, 65, (CONTENT_WIDTH - 180) / 3, (CONTENT_WIDTH - 180) / 3, (CONTENT_WIDTH - 180) / 3], styles))
        for test in tests:
            if test.laboratory or test.notes:
                story.append(_p(_date(test.tested_on) + (" / " + test.laboratory if test.laboratory else ""), styles, "subheading"))
                if test.notes:
                    story.append(_p(test.notes, styles))
    else:
        story.append(_p(_("No measured soil tests recorded."), styles))
    note(_("Nutrients are recorded in mg/kg. Compare results only when sampling and laboratory methods are comparable. Soil records do not automatically change the farm profile or crop scores."))

    section(_("Farm diary"))
    diary = list(farm.diary_entries.all())
    for entry in diary:
        story.append(_p(_date(entry.date) + " / " + entry.title, styles, "subheading"))
        story.append(_p(entry.notes, styles))
        if entry.photo:
            note(_("Photo saved in the private farm diary.") + (" " + entry.photo_caption if entry.photo_caption else ""))
    if not diary:
        story.append(_p(_("No diary entries recorded."), styles))

    section(_("Before you decide"))
    note(_("Prototype screening only. Scores are relative comparisons, not success probabilities, yield predictions, or financial forecasts. Confirm crop calendars, soil tests, drainage, irrigation and markets with a local agricultural advisor."))
    note(_("This report contains your private farm information. Share it only with people you choose."))
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=40, bottomMargin=48, title="AgriTwin AI - " + farm.name, author="AgriTwin AI", pageCompression=1)

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(48, 35, PAGE_WIDTH - 48, 35)
        label = _p("AgriTwin AI · " + _("Farm report") + " · " + _("Page") + " " + _digits(document.page), styles, "small")
        label.wrap(CONTENT_WIDTH, 25)
        label.drawOn(canvas, 48, 17)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
