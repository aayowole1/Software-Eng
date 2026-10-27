from django.shortcuts import render

from .models import Announcement

# Create your views here.
def announcement_list(request):
    announcements = Announcement.objects.all()
    return render(
        request,
        "announcement_list.html",
        {"announcements": announcements},
    )
