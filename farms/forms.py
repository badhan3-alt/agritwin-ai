from django import forms
from django.utils.translation import get_language, gettext_lazy as _
from .models import Farm, CROP_CHOICES
from .regions import REGIONS, REGIONS_BY_ID, canonical_region_id, district_choices

class RegionChoiceField(forms.ChoiceField):
    def to_python(self, value):
        return canonical_region_id(super().to_python(value))

class FarmForm(forms.ModelForm):
    region = RegionChoiceField(label=_("District / region"), choices=(), required=False, help_text=_("All 64 districts, grouped by the 8 divisions. Presets mark approximate district headquarters or city locations; adjust coordinates for your actual field."))
    current_crops = forms.MultipleChoiceField(label=_("Current crops"), choices=CROP_CHOICES, widget=forms.CheckboxSelectMultiple, help_text=_("Choose the crops in your current annual cycle. For a custom order, select the first crop below."))
    first_crop = forms.ChoiceField(label=_("First crop in your rotation"), choices=[("", _("Use the order shown above"))] + CROP_CHOICES, required=False, help_text=_("Select the crop that starts your current annual rotation."))

    class Meta:
        model = Farm
        fields = ["name", "region", "location_name", "latitude", "longitude", "farm_size_acres", "current_crops", "first_crop", "soil_type", "soil_ph", "drainage", "irrigation_availability", "farming_priority", "budget"]
        labels = {"name": _("Farm name"), "location_name": _("Location"), "latitude": _("Latitude"), "longitude": _("Longitude"), "farm_size_acres": _("Farm size (acres)"), "soil_type": _("Soil type"), "soil_ph": _("Soil pH (optional)"), "farming_priority": _("Your main priority"), "irrigation_availability": _("Irrigation access"), "drainage": _("Field drainage"), "budget": _("Budget")}
        widgets = {
            "latitude": forms.NumberInput(attrs={"step": "0.0001"}),
            "longitude": forms.NumberInput(attrs={"step": "0.0001"}),
            "farm_size_acres": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "soil_ph": forms.NumberInput(attrs={"step": "0.1", "min": "0", "max": "14", "placeholder": _("Leave blank if unknown")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["region"].choices = district_choices()
        if not self.instance.pk and not self.is_bound:
            self.initial["name"] = _("My farm")
            self.initial["location_name"] = _("Rajshahi, Bangladesh")
        if self.instance.pk and not self.is_bound:
            self.fields["first_crop"].initial = self.instance.current_crops[0]
            matched_region = next((region for region in REGIONS if region["name"] == self.instance.location_name and region["lat"] == self.instance.latitude and region["lon"] == self.instance.longitude), None)
            if matched_region:
                self.fields["region"].initial = matched_region["id"]
                if (get_language() or "").startswith("bn"):
                    self.initial["location_name"] = f"{matched_region['district_bn']}, {matched_region['division_bn']} বিভাগ, বাংলাদেশ"
            elif self.instance.location_name == "Rajshahi, Bangladesh":
                self.initial["location_name"] = _("Rajshahi, Bangladesh")
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        data = super().clean()
        region = REGIONS_BY_ID.get(data.get("region"))
        if region:
            # Presets work even without browser scripts. They identify regional
            # centers, and never infer the field's soil properties.
            data["latitude"], data["longitude"] = region["lat"], region["lon"]
            data["location_name"] = region["name"]
        crops = data.get("current_crops", [])
        first = data.get("first_crop")
        if len(crops) > 3:
            self.add_error("current_crops", _("Choose up to three crops for this annual planning prototype."))
        if first:
            if first not in crops:
                self.add_error("first_crop", _("The first crop must also be selected in your current crops."))
            else:
                data["current_crops"] = [first] + [c for c in crops if c != first]
        lat, lon = data.get("latitude"), data.get("longitude")
        if lat is not None and lon is not None and not (20.5 <= lat <= 26.7 and 88 <= lon <= 92.8):
            raise forms.ValidationError(_("This crop-calendar prototype supports Bangladesh only. Choose a location in Bangladesh."))
        return data
