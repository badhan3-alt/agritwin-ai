from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

CROP_CHOICES = [("aman_rice", _("T. Aman rice")), ("boro_rice", _("Boro rice")), ("lentil", _("Lentil")), ("mustard", _("Mustard")), ("mung_bean", _("Mung bean")), ("maize", _("Maize")), ("wheat", _("Wheat"))]
SOIL_CHOICES = [("unknown", _("Unknown / not tested")), ("clay_loam", _("Clay loam")), ("silt_loam", _("Silt loam")), ("sandy_loam", _("Sandy loam")), ("loam", _("Loam")), ("clay", _("Clay"))]
IRRIGATION_CHOICES = [("limited", _("Limited")), ("moderate", _("Moderate")), ("abundant", _("Abundant"))]
PRIORITY_CHOICES = [("water_conservation", _("Conserve water")), ("soil_health", _("Improve soil health")), ("economic_return", _("Explore economic potential")), ("climate_resilience", _("Build climate resilience"))]

def default_crops():
    return ["aman_rice", "boro_rice"]

class Farm(models.Model):
    owner_session = models.CharField(max_length=64, db_index=True, editable=False)
    name = models.CharField(max_length=120, default="My farm")
    location_name = models.CharField(max_length=160, default="Rajshahi, Bangladesh")
    latitude = models.FloatField(default=24.3745, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(default=88.6042, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    farm_size_acres = models.FloatField(default=3.0, validators=[MinValueValidator(0.01), MaxValueValidator(100000)])
    current_crops = models.JSONField(default=default_crops)
    soil_type = models.CharField(max_length=20, choices=SOIL_CHOICES, default="unknown")
    soil_ph = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(14)])
    drainage = models.CharField(max_length=20, choices=[("unknown", _("Unknown")), ("well_drained", _("Well drained")), ("poor", _("Poor / waterlogging occurs"))], default="unknown")
    irrigation_availability = models.CharField(max_length=20, choices=IRRIGATION_CHOICES, default="limited")
    farming_priority = models.CharField(max_length=30, choices=PRIORITY_CHOICES, default="water_conservation")
    budget = models.CharField(max_length=10, choices=[("low", _("Low")), ("medium", _("Medium")), ("high", _("High"))], default="medium")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        allowed = dict(CROP_CHOICES)
        if not isinstance(self.current_crops, list) or not self.current_crops or any(c not in allowed for c in self.current_crops):
            raise ValidationError({"current_crops": _("Choose at least one supported crop.")})

    def to_profile(self):
        fields = ["name", "location_name", "latitude", "longitude", "farm_size_acres", "current_crops", "soil_type", "soil_ph", "drainage", "irrigation_availability", "farming_priority", "budget"]
        return {field: getattr(self, field) for field in fields}

    @property
    def crop_names(self):
        lookup = dict(CROP_CHOICES)
        return " → ".join(str(lookup.get(c, c)) for c in self.current_crops)

    @classmethod
    def example_defaults(cls):
        return {"name": "Rajshahi example farm", "location_name": "Rajshahi, Bangladesh", "latitude": 24.3745, "longitude": 88.6042, "farm_size_acres": 3, "current_crops": ["aman_rice", "boro_rice"], "soil_type": "unknown", "soil_ph": None, "drainage": "unknown", "irrigation_availability": "limited", "farming_priority": "water_conservation", "budget": "medium"}

class Analysis(models.Model):
    farm = models.OneToOneField(Farm, related_name="analysis", on_delete=models.CASCADE)
    climate = models.JSONField(default=dict)
    strategies = models.JSONField(default=list)
    analyzed_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Analysis: {self.farm.name}"
