from django.contrib import admin

from .models import Committee, CommitteeMember


class CommitteeMemberInline(admin.TabularInline):
    model = CommitteeMember
    extra = 0


@admin.register(Committee)
class CommitteeAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "created_at")
    inlines = [CommitteeMemberInline]
