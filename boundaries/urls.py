from django.urls import path
from . import views

app_name = "boundaries"
urlpatterns = [
    path("", views.editor, name="editor"),
    path("delete/", views.delete, name="delete"),
    path("download/", views.download, name="download"),
]
