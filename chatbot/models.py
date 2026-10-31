from django.db import models

class Conversation(models.Model):
    owner_session = models.CharField(max_length=64, db_index=True, editable=False)
    title = models.CharField(max_length=120)
    farm = models.ForeignKey("farms.Farm", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]

    def __str__(self):
        return self.title

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, related_name="messages", on_delete=models.CASCADE)
    role = models.CharField(max_length=12, choices=[("user", "Farmer"), ("assistant", "Assistant")])
    body = models.TextField()
    mode = models.CharField(max_length=12, blank=True, default="")
    sources = models.JSONField(default=list, blank=True)
    notice = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
