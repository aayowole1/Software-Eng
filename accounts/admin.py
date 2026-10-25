from django.contrib import admin
from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_suspended", "created_at")
    list_filter = ("role", "is_suspended")
    readonly_fields = ("is_suspended",)
