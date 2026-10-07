from django.contrib import admin

from .models import MembershipApplication


@admin.register(MembershipApplication)
class MembershipApplicationAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "submitted_at", "reviewed_by")
    list_filter = ("status",)
