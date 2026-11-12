from django.contrib import admin

from .models import Announcement, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "committee", "slug")
    list_filter = ("committee",)
    search_fields = ("name", "slug")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "committee", "status", "author")
    list_filter = ("committee", "status", "category")
    search_fields = ("title", "content")
