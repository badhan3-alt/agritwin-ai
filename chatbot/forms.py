from django import forms
from django.utils.translation import gettext_lazy as _
from core.localization import localize_text
from farms.models import Farm

class ChatForm(forms.Form):
    conversation = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput)
    message = forms.CharField(label=_("Your question"), max_length=2000, strip=True, widget=forms.Textarea(attrs={"rows": 3, "placeholder": _("Ask about your crops, soil, water, or farm plan…"), "class": "chat-textarea", "maxlength": 2000}))
    farm = forms.ModelChoiceField(queryset=Farm.objects.none(), required=False, label=_("Choose your farm"), empty_label=_("No farm selected"))
    include_farm = forms.BooleanField(required=False, label=_("Use my selected farm information in this chat"), initial=False)

    def __init__(self, *args, farms=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["farm"].queryset = farms if farms is not None else Farm.objects.none()
        self.fields["farm"].label_from_instance = lambda farm: str(localize_text(farm.name))
        self.fields["farm"].widget.attrs["class"] = "form-control"

    def clean(self):
        data = super().clean()
        if data.get("include_farm") and not data.get("farm"):
            self.add_error("farm", _("Choose a farm before including its information."))
        return data
