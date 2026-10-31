"""Farmer-facing translations of canonical scientific service output."""
from django import template
from core.localization import localize_text
from django.utils.translation import get_language

register = template.Library()
register.filter("localize_text", localize_text)

@register.filter
def bn_number(value):
    """Bengali display digits; never apply to input values, URLs, or CSS."""
    text = str(value)
    if (get_language() or "").startswith("bn"):
        return text.translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))
    return text
