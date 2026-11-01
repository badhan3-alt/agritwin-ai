from django.urls import path
from . import views

app_name = "notebook"
urlpatterns = [
    path("calendar/", views.records, {"section": "calendar"}, name="calendar"),
    path("ledger/", views.records, {"section": "ledger"}, name="ledger"),
    path("diary/", views.records, {"section": "diary"}, name="diary"),
    path("soil/", views.records, {"section": "soil"}, name="soil"),
    path("calendar/<int:entry_id>/complete/", views.complete_event, name="complete"),
    path("diary/<int:entry_id>/photo/", views.diary_photo, name="photo"),
    path("<str:section>/new/", views.entry_form, name="create"),
    path("<str:section>/<int:entry_id>/edit/", views.entry_form, name="edit"),
    path("<str:section>/<int:entry_id>/delete/", views.delete_entry, name="delete"),
]
