from django.urls import path
from . import views
app_name = "farms"
urlpatterns = [
    path("", views.farm_list, name="list"),
    path("new/", views.create, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/edit/", views.edit, name="edit"),
    path("<int:pk>/delete/", views.delete, name="delete"),
]
