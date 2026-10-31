from django.urls import path
from . import views
app_name = "core"
urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("demo/", views.demo, name="demo"),
    path("language/", views.language, name="language"),
    path("health/", views.health, name="health"),
    path("api/health/", views.health),
]
