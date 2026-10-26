from django.contrib import admin

from .models import ActionItem, MeetingDraft, generation_filter


class ActionItemInline(admin.TabularInline):
    model = ActionItem
    extra = 0
    readonly_fields = ("description", "accepted", "position", "generation_token")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        parent = getattr(self, "parent_draft", None)
        return queryset.filter(generation_filter(parent.generation_token)) if parent else queryset.none()

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MeetingDraft)
class MeetingDraftAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "created_by", "created_at")
    list_filter = ("status",)
    inlines = [ActionItemInline]
    readonly_fields = tuple(field.name for field in MeetingDraft._meta.fields)

    def get_inline_instances(self, request, obj=None):
        instances = super().get_inline_instances(request, obj)
        for inline in instances:
            inline.parent_draft = obj
        return instances

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
