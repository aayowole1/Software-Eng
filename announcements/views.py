"""
@brief      Manage the UI for the announcements page.

@citation   Google Stitch was used to develop this code.
"""

# === IMPORTS
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.db.models import F, Q

from accounts.models import Profile, Role

from .models import Announcement, AnnouncementAttachment, AnnouncementReadReceipt, Category
from .forms import AnnouncementForm, AnnouncementAttachmentForm


# === HELPERS
def is_officer_or_admin(user) -> bool:
    """Check whether user has admin publishing permissions."""
    return (
        user.is_authenticated
        and (
            user.is_staff
            or user.groups.filter(name="Officer").exists()
        )
    )


def get_author_role(user) -> str:
    """Return the display label used for an announcement author."""
    if user.is_superuser:
        return "System Administrator"

    try:
        profile = user.profile
    except Profile.DoesNotExist:
        profile = None
    if profile and profile.role in {Role.ADMIN, Role.OFFICER}:
        return profile.get_role_display()

    return "Officer"


# === [ADMIN] CREATE ANNOUNCEMENT
@login_required
@user_passes_test(is_officer_or_admin, login_url="announcements:list")
def announcement_create(request):
    """Create an announcement."""
    if request.method == "POST":
        form = AnnouncementForm(request.POST)
        # support multi-file upload
        files = request.FILES.getlist("attachments")

        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.author = request.user

            announcement.author_role = get_author_role(request.user)

            # auto-set published_at if publishing immediately
            if announcement.status == "published" and not announcement.published_at:
                announcement.published_at = timezone.now()

            announcement.save()

            # handle file attachments
            for uploaded_file in files:
                # helper: format file size
                size_mb = uploaded_file.size / (1024 * 1024)
                size_label = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{int(uploaded_file.size / 1024)} KB"

                AnnouncementAttachment.objects.create(
                    announcement=announcement,
                    file=uploaded_file,
                    name=uploaded_file.name,
                    size_label=size_label
                )

            messages.success(request, f'Announcement "{announcement.title}" created successfully.')
            return redirect("announcements:detail", pk=announcement.pk)

        else:
            messages.error(request, "Please correct the errors indicated below.")

    else:
        # pre-populate sensible defaults
        form = AnnouncementForm(
            initial={
                "status": "published",
                "target_reach": 165,
            }
        )

    return render(
        request,
        "announcements/announcement_form.html",
        {
            "form": form,
            "action_title": "Create New Announcement",
            "is_edit": False,
        }
    )


# === [ADMIN] EDIT ANNOUNCEMENT
@login_required
@user_passes_test(is_officer_or_admin, login_url="announcements:list")
def announcement_edit(request, pk):
    announcement = get_object_or_404(
        Announcement.objects.prefetch_related("attachments"),
        pk=pk
    )

    # Editing is limited to the announcement author and superusers.
    if not (
        request.user.is_superuser
        or announcement.author == request.user
    ):
        raise PermissionDenied("You do not have permission to edit this announcement.")

    if request.method == "POST":
        form = AnnouncementForm(request.POST, instance=announcement)
        files = request.FILES.getlist("attachments")
        delete_attachment_ids = request.POST.getlist("delete_attachments")

        if form.is_valid():
            announcement = form.save(commit=False)

            # handle status switch to published
            if announcement.status == "published" and not announcement.published_at:
                announcement.published_at = timezone.now()

            announcement.save()

            # delete selected attachments
            if delete_attachment_ids:
                AnnouncementAttachment.objects.filter(
                    id__in=delete_attachment_ids,
                    announcement=announcement
                ).delete()

            # add newly uploaded attachments
            for uploaded_file in files:
                size_mb = uploaded_file.size / (1024 * 1024)
                size_label = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{int(uploaded_file.size / 1024)} KB"
                AnnouncementAttachment.objects.create(
                    announcement=announcement,
                    file=uploaded_file,
                    name=uploaded_file.name,
                    size_label=size_label
                )

            messages.success(request, f'Changes to "{announcement.title}" have been saved.')
            return redirect("announcements:detail", pk=announcement.pk)

        else:
            messages.error(request, 'Please correct the form errors.')

    else:
        form = AnnouncementForm(instance=announcement)

    return render(
        request,
        "announcements/announcement_form.html",
        {
            "form": form,
            "announcement": announcement,
            "action_title": f"Edit Announcement: {announcement.title}",
            "is_edit": True,
            "existing_attachments": announcement.attachments.all(),
        }
    )

# === [ALL] LIST ANNOUNCEMENTS
@login_required
def announcements_list(request):
    is_admin = (
        request.user.is_staff
        or request.user.groups.filter(name="Officer").exists()
    )

    # define filtering and search feature
    query = request.GET.get("q", "")
    category_slug = request.GET.get("category", "")
    status_filter = request.GET.get("status", "all")

    announcements = Announcement.objects.select_related(
        "author", "category"
    ).prefetch_related("attachments")


    if not is_admin:
        # regular members can only see published posts
        announcements = announcements.filter(status="published")
    elif status_filter != "all":
        announcements = announcements.filter(status=status_filter)

    if query:
        announcements = announcements.filter(
            Q(title__icontains=query)
            | Q(content__icontains=query)
        )

    if category_slug:
        announcements = announcements.filter(category__slug=category_slug)

    # display summary stats in admin view
    stats = {}
    if is_admin:
        stats = {
            "total_published": Announcement.objects.filter(status="published").count(),
            "active_drafts": Announcement.objects.filter(status="draft").count(),
            "scheduled_queue": Announcement.objects.filter(status="scheduled").count(),
            "avg_read_rate": 87,  # calculated from read receipts TODO: see if this needs to be changed
        }

    categories = Category.objects.all()

    context = {
        "announcements": announcements,
        "categories": categories,
        "is_admin": is_admin,
        "stats": stats,
        "current_category": category_slug,
        "search_query": query,
        "status_filter": status_filter,
    }

    return render(
        request,
        "announcements/announcements_page.html",
        context,
    )

# === [ALL] DISPLAY ANNOUNCEMENT DETAIL
@login_required
def announcement_detail(request, pk):
    """Retrieve details about the announcement."""
    announcement = get_object_or_404(
        Announcement.objects.select_related(
            "author", "category").prefetch_related("attachments"),
        pk=pk
    )

    is_admin = is_officer_or_admin(request.user)
    is_published = Announcement.objects.filter(
        pk=announcement.pk,
        status="published",
    ).exists()

    # permission check: regular members cannot view unpublished/draft posts
    if not is_published and not is_admin:
        raise PermissionDenied("This announcement has not been published yet.")

    # record / check read receipt for telemetry
    receipt_created = False
    if request.user.is_authenticated:
        receipt, created = AnnouncementReadReceipt.objects.get_or_create(
            user=request.user,
            announcement=announcement
        )
        if created:
            # atomic increment read count
            Announcement.objects.filter(pk=pk).update(read_count=F("read_count") + 1)
            announcement.refresh_from_db(fields=["read_count"])
            receipt_created = True

    is_read_by_user = AnnouncementReadReceipt.objects.filter(
        user=request.user,
        announcement=announcement
    ).exists()

    # related / recent notices in the same category
    related_announcements = Announcement.objects.filter(
        category=announcement.category,
        status="published"
    ).exclude(pk=announcement.pk).order_by("-published_at")[:3]

    context = {
        "announcement": announcement,
        "is_admin": is_admin,
        "can_edit": is_admin and (
            request.user.is_superuser
            or announcement.author == request.user
        ),
        "is_read_by_user": is_read_by_user,
        "receipt_just_created": receipt_created,
        "related_announcements": related_announcements,
    }

    return render(request, "announcements/announcement_detail.html", context)


# === [DISPLAY] MARK AS READ TOGGLE
@login_required
def announcement_mark_read(request, pk):
    if request.method == "POST":
        announcement = get_object_or_404(Announcement, pk=pk)
        receipt, created = AnnouncementReadReceipt.objects.get_or_create(
            user=request.user,
            announcement=announcement
        )
        if created:
            Announcement.objects.filter(pk=pk).update(read_count=F("read_count") + 1)
            announcement.refresh_from_db(fields=["read_count"])

        # return updated read button HTML or JSON response
        return redirect("announcements:list")

    return redirect("announcements:list")
