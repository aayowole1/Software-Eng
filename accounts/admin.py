from django.contrib import admin
from .models import Profile, Role, get_role


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_suspended", "created_at")
    list_filter = ("role", "is_suspended")
    # Role writes use Users and Roles so Django admin cannot bypass the audit.
    readonly_fields = (
        "user", "role", "is_suspended", "created_at", "role_version", "role_history",
        "suspension_was_active", "suspension_restore_active", "suspension_version", "suspension_update_pending",
    )

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return get_role(request.user) == Role.ADMIN and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
