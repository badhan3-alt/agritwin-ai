from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import DiaryEntry


@receiver(post_delete, sender=DiaryEntry)
def delete_diary_photo(sender, instance, **kwargs):
    if instance.photo:
        storage, name = instance.photo.storage, instance.photo.name
        transaction.on_commit(lambda: storage.delete(name))
