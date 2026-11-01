from django.urls import path
from . import views

app_name = "weather"
urlpatterns = [
    path("<int:pk>/", views.dashboard, name="dashboard"),
    path("<int:pk>/refresh/", views.refresh, name="refresh"),
]
