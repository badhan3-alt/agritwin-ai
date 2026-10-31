from django.contrib import admin
from .models import Farm, Analysis

@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ["name", "location_name", "farm_size_acres", "updated_at"]
    list_filter = ["irrigation_availability", "soil_type"]
    search_fields = ["name", "location_name"]
    readonly_fields = ["owner_session", "created_at", "updated_at"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            # A subsequent dashboard request must describe the edited inputs.
            Analysis.objects.filter(farm=obj).delete()

@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ["farm", "analyzed_at"]
    readonly_fields = ["analyzed_at"]
