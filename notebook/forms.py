import io
import warnings

from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import CalendarEvent, DiaryEntry, LedgerEntry, SoilTest


class RecordForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
            if isinstance(field, forms.DateField):
                field.widget = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"})
            if isinstance(field, forms.CharField) and isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = 4


class CalendarEventForm(RecordForm):
    class Meta:
        model = CalendarEvent
        fields = ["title", "event_type", "crop", "due_date", "reminder_days", "notes", "completed"]


class LedgerEntryForm(RecordForm):
    class Meta:
        model = LedgerEntry
        fields = ["date", "entry_type", "title", "category", "amount", "notes"]
        widgets = {"amount": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"})}


class DiaryEntryForm(RecordForm):
    photo = forms.FileField(label=_("Photo (optional)"), required=False, widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png"}), help_text=_("JPEG or PNG, up to 5 MB. Photos are visible only to this farm's owner."))
    remove_photo = forms.BooleanField(label=_("Remove saved photo"), required=False)

    class Meta:
        model = DiaryEntry
        fields = ["date", "title", "notes", "photo", "remove_photo", "photo_caption"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.photo:
            self.fields.pop("remove_photo")

    def clean(self):
        data = super().clean()
        if data.get("remove_photo"):
            if "photo" in self.changed_data:
                self.add_error("photo", _("Choose either a replacement photo or removal."))
            else:
                data["photo"] = False
        return data

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if not photo or not hasattr(photo, "content_type"):
            return photo
        if photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError(_("Choose a photo smaller than 5 MB."))
        try:
            content = photo.read()
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as original:
                    if original.format not in {"JPEG", "PNG"}:
                        raise ValueError("Unsupported format")
                    if original.width * original.height > 20_000_000:
                        raise ValueError("Image too large")
                    original.verify()
                with Image.open(io.BytesIO(content)) as original:
                    original.load()
                    pixels = ImageOps.exif_transpose(original)
                    # Re-encode the decoded pixels, removing metadata and any
                    # arbitrary bytes appended to the uploaded file.
                    if pixels.mode not in {"RGB", "RGBA"}:
                        pixels = pixels.convert("RGB")
                    clean_pixels = Image.frombytes(pixels.mode, pixels.size, pixels.tobytes())
                    output = io.BytesIO()
                    clean_pixels.save(output, format="PNG")
            if output.tell() > 5 * 1024 * 1024:
                raise ValueError("Decoded photo too large")
            return SimpleUploadedFile("photo.png", output.getvalue(), content_type="image/png")
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise forms.ValidationError(_("Upload a valid JPEG or PNG photo, at most 20 megapixels and 5 MB."))


class SoilTestForm(RecordForm):
    class Meta:
        model = SoilTest
        fields = ["tested_on", "laboratory", "ph", "nitrogen", "phosphorus", "potassium", "notes"]
        widgets = {field: forms.NumberInput(attrs={"step": "0.01", "min": "0", **({"max": "14"} if field == "ph" else {})}) for field in ["ph", "nitrogen", "phosphorus", "potassium"]}
