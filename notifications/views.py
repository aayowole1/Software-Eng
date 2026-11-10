from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user).select_related()
    unread_count = notifications.filter(is_read=False).count()
    return render(request, "notifications/notification_list.html", {
        "notifications": notifications,
        "unread_count": unread_count,
    })


@login_required
def notification_read(request, pk):
    """Mark a single notification read and redirect to the linked resource."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notification.is_read:
        Notification.objects.filter(pk=pk, user=request.user).update(is_read=True)
        notification.is_read = True
    return redirect(notification.get_target_url())


@require_POST
@login_required
def mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect("notifications:list")
