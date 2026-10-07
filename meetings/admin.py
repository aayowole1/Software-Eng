from django.contrib import admin

from .models import ActionItem, MeetingDraft


class ActionItemInline(admin.TabularInline):
    model = ActionItem
    extra = 0


@admin.register(MeetingDraft)
class MeetingDraftAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "created_by", "created_at")
    list_filter = ("status",)
    inlines = [ActionItemInline]
