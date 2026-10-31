from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("farms/", include("farms.urls")),
    path("climate/", include("climate.urls")),
    path("rotations/", include("rotations.urls")),
    path("simulator/", include("simulator.urls")),
    path("reports/", include("reports.urls")),
    path("chatbot/", include("chatbot.urls")),
]
