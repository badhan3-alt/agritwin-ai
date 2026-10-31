from django.urls import path
from . import views
app_name = "climate"
urlpatterns = [
    path("<int:pk>/", views.dashboard, name="dashboard"),
    path("<int:pk>/refresh/", views.refresh, name="refresh"),
    path("<int:pk>/source/", views.nasa_source, name="nasa_source"),
]
