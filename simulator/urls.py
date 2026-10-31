from django.urls import path
from . import views
app_name = "simulator"
urlpatterns = [path("<int:pk>/", views.workbench, name="workbench")]
