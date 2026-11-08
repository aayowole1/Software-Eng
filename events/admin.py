from django.contrib import admin

from .models import Attendance, Event, RSVP


class RSVPInline(admin.TabularInline):
    model = RSVP
    extra = 0


class AttendanceInline(admin.TabularInline):
    model = Attendance
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "starts_at", "location", "cancelled")
    list_filter = ("cancelled",)
    inlines = [RSVPInline, AttendanceInline]
