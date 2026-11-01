from django import forms
from django.utils.translation import gettext_lazy as _
from .geometry import SQUARE_METRES_PER_ACRE, measure, validate_geometry
from .models import FarmBoundary


class BoundaryForm(forms.ModelForm):
    use_estimated_area = forms.BooleanField(required=False, label=_("Update farm size from this boundary"), help_text=_("Replaces the saved farm area with the estimate. Your NASA analysis is unchanged because area is not a scoring input."))

    class Meta:
        model = FarmBoundary
        fields = ["geometry"]
        labels = {"geometry": _("Boundary coordinates (GeoJSON)")}
        help_texts = {"geometry": _("Longitude first, latitude second. Draw on the map or enter a Polygon with one closed ring. Saved area is an estimate, not a land survey.")}
        widgets = {"geometry": forms.Textarea(attrs={"rows": 7, "class": "form-control", "spellcheck": "false", "maxlength": 40000})}

    def clean_geometry(self):
        value = self.cleaned_data["geometry"]
        # Validate before ModelForm assigns data to an existing boundary. This
        # also makes derived-area checks safe for every submitted JSON type.
        validate_geometry(value)
        # Retain only the supported GeoJSON keys; no unrelated upload metadata.
        return {"type": value["type"], "coordinates": value["coordinates"]}

    def clean(self):
        data = super().clean()
        if data.get("use_estimated_area") and "geometry" in data:
            if measure(data["geometry"])[0] / SQUARE_METRES_PER_ACRE < 0.01:
                self.add_error("use_estimated_area", _("This boundary is smaller than the minimum farm size of 0.01 acres. Save it without updating farm size."))
        return data
