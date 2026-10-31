from django.urls import path
from . import views
app_name = "reports"
urlpatterns = [path("<int:pk>/", views.detail, name="detail"), path("<int:pk>/download/<str:format>/", views.download, name="download")]
