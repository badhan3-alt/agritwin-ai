import uuid
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class FarmRecord(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CalendarEvent(FarmRecord):
    TYPES = [("planting", _("Planting")), ("irrigation", _("Irrigation")), ("fertilizer", _("Fertilizer application")), ("harvest", _("Harvesting")), ("other", _("Other task"))]
    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE, related_name="calendar_events")
    title = models.CharField(_("Task"), max_length=160)
    event_type = models.CharField(_("Activity"), max_length=16, choices=TYPES)
    crop = models.CharField(_("Crop / field"), max_length=120, blank=True)
    due_date = models.DateField(_("Planned date"))
    reminder_days = models.PositiveSmallIntegerField(_("Remind me this many days before"), default=1, validators=[MaxValueValidator(30)])
    notes = models.TextField(_("Notes"), blank=True, max_length=5000)
    completed = models.BooleanField(_("Completed"), default=False)

    class Meta:
        ordering = ["completed", "due_date", "pk"]

    @property
    def status(self):
        if self.completed:
            return "completed"
        today = timezone.localdate()
        if self.due_date < today:
            return "overdue"
        if self.due_date == today:
            return "today"
        return "upcoming"

    @property
    def reminder_due(self):
        return not self.completed and self.due_date <= timezone.localdate() + timezone.timedelta(days=self.reminder_days)

    def __str__(self):
        return self.title


class LedgerEntry(FarmRecord):
    TYPES = [("expense", _("Expense")), ("income", _("Income / sale"))]
    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE, related_name="ledger_entries")
    date = models.DateField(_("Date"), default=timezone.localdate)
    entry_type = models.CharField(_("Record type"), choices=TYPES, max_length=12)
    title = models.CharField(_("Description"), max_length=160)
    category = models.CharField(_("Category"), max_length=100, blank=True, help_text=_("For example: seed, labor, irrigation, fertilizer, or crop sales."))
    amount = models.DecimalField(_("Amount (BDT)"), max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    notes = models.TextField(_("Notes"), blank=True, max_length=5000)

    class Meta:
        ordering = ["-date", "-pk"]

    def __str__(self):
        return self.title


def diary_photo_path(instance, filename):
    return f"diary/{instance.farm_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class DiaryEntry(FarmRecord):
    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE, related_name="diary_entries")
    date = models.DateField(_("Observation date"), default=timezone.localdate)
    title = models.CharField(_("Title"), max_length=160)
    notes = models.TextField(_("Notes and observations"), max_length=10000)
    photo = models.FileField(_("Photo"), upload_to=diary_photo_path, blank=True, max_length=200)
    photo_caption = models.CharField(_("Photo description"), max_length=240, blank=True)

    class Meta:
        ordering = ["-date", "-pk"]

    def __str__(self):
        return self.title


class SoilTest(FarmRecord):
    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE, related_name="soil_tests")
    tested_on = models.DateField(_("Test date"), default=timezone.localdate)
    laboratory = models.CharField(_("Laboratory / source"), max_length=160, blank=True)
    ph = models.DecimalField(_("pH"), max_digits=4, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0), MaxValueValidator(14)])
    nitrogen = models.DecimalField(_("Nitrogen (mg/kg)"), max_digits=9, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0)])
    phosphorus = models.DecimalField(_("Phosphorus (mg/kg)"), max_digits=9, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0)])
    potassium = models.DecimalField(_("Potassium (mg/kg)"), max_digits=9, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0)])
    notes = models.TextField(_("Method, sample location, and notes"), blank=True, max_length=5000)

    class Meta:
        ordering = ["-tested_on", "-pk"]

    def clean(self):
        super().clean()
        if all(getattr(self, field) is None for field in ("ph", "nitrogen", "phosphorus", "potassium")):
            raise ValidationError(_("Enter at least one measured soil result."))
        if self.tested_on and self.tested_on > timezone.localdate():
            raise ValidationError({"tested_on": _("A soil test date cannot be in the future.")})

    def __str__(self):
        return f"{self.farm}: {self.tested_on}"
