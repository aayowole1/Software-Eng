from django.contrib import admin

# Register your models here.
from .models import Announcement

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "creator", "created_at")
    search_fields = ("title", "description")

