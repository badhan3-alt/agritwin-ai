from django import forms
from django.utils.translation import gettext_lazy as _
from farms.models import IRRIGATION_CHOICES, PRIORITY_CHOICES

class ScenarioForm(forms.Form):
    rainfall_delta_pct = forms.FloatField(label=_("Rainfall change (%)"), min_value=-50, max_value=50, initial=-20, widget=forms.NumberInput(attrs={"type": "range", "min": -50, "max": 50, "step": 5}))
    temp_delta_c = forms.FloatField(label=_("Temperature change (°C)"), min_value=-1, max_value=5, initial=2, widget=forms.NumberInput(attrs={"type": "range", "min": -1, "max": 5, "step": 0.5}))
    irrigation = forms.ChoiceField(choices=IRRIGATION_CHOICES, label=_("Scenario irrigation access"))
    priority = forms.ChoiceField(choices=PRIORITY_CHOICES, label=_("Scenario priority"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
