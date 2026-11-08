"""Durable ownership evidence for interrupted account provisioning.

This journal deliberately contains no passwords, credentials or provider tokens.
The reserved keys are written before creating the User, including its signals.
"""

from django.db import models
from django_mongodb_backend.fields import ObjectIdField


class SignupAttempt(models.Model):
    class Channel(models.TextChoices):
        PASSWORD = "password", "Password"
        GOOGLE = "google", "Google"

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        COMPENSATED = "compensated", "Compensated"

    reserved_user_id = ObjectIdField(unique=True)
    application_id = ObjectIdField(unique=True)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    username = models.CharField(max_length=150)
    email = models.EmailField(max_length=254)
    statement = models.TextField()
    google_subject = models.CharField(max_length=255, blank=True, default="")
    state = models.CharField(max_length=20, choices=State.choices, default=State.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        # An opaque reference is safe to use in an operator recovery alert.
        return f"Signup attempt {self.pk} ({self.state})"
