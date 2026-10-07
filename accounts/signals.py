from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile, Role


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    """Give every new user a Profile; superusers start as admins."""
    if created:
        role = Role.ADMIN if instance.is_superuser else Role.APPLICANT
        Profile.objects.get_or_create(user=instance, defaults={"role": role})
