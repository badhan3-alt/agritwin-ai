from django.urls import path
from . import views
app_name = "rotations"
urlpatterns = [path("<int:pk>/", views.explorer, name="explorer")]
