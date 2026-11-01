from django.contrib import admin
from .models import CalendarEvent, DiaryEntry, LedgerEntry, SoilTest

for model in [CalendarEvent, DiaryEntry, LedgerEntry, SoilTest]:
    admin.site.register(model)
