from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from farms.services import owned_farm
from .forms import CalendarEventForm, DiaryEntryForm, LedgerEntryForm, SoilTestForm
from .models import CalendarEvent, DiaryEntry, LedgerEntry, SoilTest
from .services import ledger_totals, soil_comparison


SECTIONS = {
    "calendar": {"model": CalendarEvent, "form": CalendarEventForm, "label": _lazy("Crop calendar"), "new_label": _lazy("Add task")},
    "ledger": {"model": LedgerEntry, "form": LedgerEntryForm, "label": _lazy("Expenses and income"), "new_label": _lazy("Add transaction")},
    "diary": {"model": DiaryEntry, "form": DiaryEntryForm, "label": _lazy("Farm diary"), "new_label": _lazy("Add diary entry")},
    "soil": {"model": SoilTest, "form": SoilTestForm, "label": _lazy("Soil test records"), "new_label": _lazy("Add soil test")},
}


def section_config(section):
    if section not in SECTIONS:
        raise Http404
    return SECTIONS[section]


@require_GET
def records(request, pk, section):
    farm = owned_farm(request, pk)
    config = section_config(section)
    entries = config["model"].objects.filter(farm=farm)
    context = {"farm": farm, "section": section, "section_label": config["label"], "new_label": config["new_label"], "entries": entries, "active_page": section}
    if section == "calendar":
        today = timezone.localdate()
        context.update({"today": today, "overdue_count": entries.filter(completed=False, due_date__lt=today).count(), "today_count": entries.filter(completed=False, due_date=today).count(), "reminders": [entry for entry in entries.filter(completed=False) if entry.reminder_due]})
    elif section == "ledger":
        context.update(ledger_totals(farm))
    elif section == "soil":
        context["comparisons"] = soil_comparison(entries)
    return render(request, f"notebook/{section}.html", context)


@require_http_methods(["GET", "POST"])
def entry_form(request, pk, section, entry_id=None):
    farm = owned_farm(request, pk)
    config = section_config(section)
    entry = get_object_or_404(config["model"], pk=entry_id, farm=farm) if entry_id is not None else config["model"](farm=farm)
    old_photo = entry.photo.name if section == "diary" and entry.photo else None
    # Validation assigns uploaded files to the ModelForm instance even when
    # another field fails. Only the persisted photo has a preview endpoint.
    saved_photo_url = reverse("notebook:photo", kwargs={"pk": pk, "entry_id": entry.pk}) if old_photo and entry.pk else None
    saved_photo_alt = (entry.photo_caption or entry.title) if saved_photo_url else ""
    form = config["form"](request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None, instance=entry)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            saved = form.save()
            if old_photo and saved.photo.name != old_photo:
                storage = saved.photo.storage
                transaction.on_commit(lambda: storage.delete(old_photo))
        messages.success(request, _("Farm record saved."))
        return redirect(f"notebook:{section}", pk=pk)
    return render(request, "notebook/form.html", {"farm": farm, "section": section, "section_label": config["label"], "new_label": config["new_label"], "form": form, "editing": entry_id is not None, "active_page": section, "return_url": reverse(f"notebook:{section}", kwargs={"pk": pk}), "saved_photo_url": saved_photo_url, "saved_photo_alt": saved_photo_alt})


@require_POST
def delete_entry(request, pk, section, entry_id):
    farm = owned_farm(request, pk)
    config = section_config(section)
    entry = get_object_or_404(config["model"], pk=entry_id, farm=farm)
    entry.delete()
    messages.success(request, _("Farm record deleted."))
    return redirect(f"notebook:{section}", pk=pk)


@require_POST
def complete_event(request, pk, entry_id):
    farm = owned_farm(request, pk)
    event = get_object_or_404(CalendarEvent, pk=entry_id, farm=farm)
    # Explicit target value keeps repeated submissions idempotent.
    event.completed = request.POST.get("completed") == "1"
    event.save(update_fields=["completed", "updated_at"])
    messages.success(request, _("Task status updated."))
    return redirect("notebook:calendar", pk=pk)


@require_GET
def diary_photo(request, pk, entry_id):
    farm = owned_farm(request, pk)
    entry = get_object_or_404(DiaryEntry, pk=entry_id, farm=farm)
    if not entry.photo:
        raise Http404
    try:
        response = FileResponse(entry.photo.open("rb"), content_type="image/png")
    except (OSError, ValueError):
        raise Http404
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = 'inline; filename="farm-observation.png"'
    return response
