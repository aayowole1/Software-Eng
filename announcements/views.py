"""
@brief      Manage the UI for the announcements page.

@citation   Google Stitch was used to develop this code.
"""

# === IMPORTS
from bson import ObjectId
from bson.errors import InvalidId
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import FileResponse, JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.db.models import F, Q
from django.views.decorators.http import require_POST

from accounts.models import Profile, ROSTER_ROLES, Role, get_role

from .models import (
    Announcement,
    AnnouncementAttachment,
    AnnouncementComment,
    AnnouncementReadReceipt,
    Category,
)
from .forms import AnnouncementForm, AnnouncementAttachmentForm, AnnouncementCommentForm
from .permissions import (
    announcement_access,
    effective_role,
    visible_announcements,
)


# === HELPERS
def is_officer_or_admin(user) -> bool:
    """Check whether user has admin publishing permissions."""
    return (
        user.is_authenticated
        and (
            get_role(user) in {Role.OFFICER, Role.ADMIN}
        )
    )


def officer_view_access(view):
    """Require officer privileges while preserving member redirect behavior."""
    @login_required
    def checked(request, *args, **kwargs):
        if not request.user.is_superuser and (
            request.user.is_staff
            or request.user.groups.filter(name="Officer").exists()
        ):
            raise PermissionDenied("Legacy account flags do not grant access.")
        if effective_role(request.user) not in {Role.OFFICER, Role.ADMIN}:
            if not hasattr(request, "session"):
                raise PermissionDenied("You do not have officer access.")
            return redirect(
                f"{reverse('announcements:list')}?next={request.get_full_path()}"
            )
        return view(request, *args, **kwargs)
    return checked


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


def can_receive_announcement(user, announcement) -> bool:
    """Return whether a user belongs to an announcement's audience."""
    if announcement.committee_id is None:
        return True

    return announcement.committee.members.filter(user=user).exists()


def publish_due_announcements() -> int:
    """Publish scheduled announcements whose release time has arrived."""
    now = timezone.now()
    due_announcements = Announcement.objects.filter(
        status="scheduled",
        scheduled_for__lte=now,
    )
    published_count = 0
    for announcement in due_announcements:
        published_count += Announcement.objects.filter(
            pk=announcement.pk, status="scheduled", scheduled_for__lte=now,
        ).update(status="published", published_at=now, updated_at=now)
    return published_count


@announcement_access(Role.MEMBER)
def announcement_attachment_download(request, pk):
    """Serve an attachment to users who can access its announcement."""
    attachment = get_object_or_404(
        AnnouncementAttachment.objects.select_related("announcement"),
        pk=pk,
    )
    announcement = attachment.announcement
    is_admin = is_officer_or_admin(request.user)
    if not is_admin and (
        announcement.status != "published"
        or not can_receive_announcement(request.user, announcement)
    ):
        raise PermissionDenied(
            "You do not have permission to download this attachment."
        )
    return FileResponse(
        attachment.file.open("rb"),
        as_attachment=True,
        filename=attachment.name,
        headers={"Cache-Control": "private, no-store"},
    )


# === [ADMIN] CREATE ANNOUNCEMENT
@officer_view_access
def announcement_create(request):
    """Create an announcement."""
    if request.method == "POST":
        form = AnnouncementForm(request.POST, user=request.user)
        save_action = request.POST.get("save_action", "publish")
        # support multi-file upload
        files = request.FILES.getlist("attachments")

        if len(files) > 5:
            messages.error(request, "Upload up to 5 files.")
            return render(
                request,
                "announcements/announcement_form.html",
                {
                    "form": form,
                    "action_title": "Create New Announcement",
                    "is_edit": False,
                },
            )

        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.author = request.user
            if save_action == "draft":
                announcement.status = "draft"
            else:
                announcement.status = (
                    "scheduled" if announcement.scheduled_for else "published"
                )

            announcement.author_role = get_author_role(request.user)

            if announcement.status == "published":
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
            user=request.user,
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
@officer_view_access
def announcement_edit(request, pk):
    announcement = get_object_or_404(
        Announcement.objects.prefetch_related("attachments"),
        pk=pk
    )

    # Editing is limited to the announcement author and superusers.
    if not (
        request.user.is_superuser
        or get_role(request.user) == Role.ADMIN
        or announcement.author == request.user
    ):
        raise PermissionDenied("You do not have permission to edit this announcement.")

    if request.method == "POST":
        form = AnnouncementForm(
            request.POST,
            instance=announcement,
            user=request.user,
        )
        save_action = request.POST.get("save_action", "publish")
        files = request.FILES.getlist("attachments")
        delete_attachment_ids = request.POST.getlist("delete_attachments")

        if len(files) > 5:
            messages.error(request, "Upload up to 5 files.")
            return render(
                request,
                "announcements/announcement_form.html",
                {
                    "form": form,
                    "announcement": announcement,
                    "action_title": f"Edit Announcement: {announcement.title}",
                    "is_edit": True,
                    "existing_attachments": announcement.attachments.all(),
                },
            )

        if form.is_valid():
            announcement = form.save(commit=False)
            if save_action == "draft":
                announcement.status = "draft"
            else:
                announcement.status = (
                    "scheduled" if announcement.scheduled_for else "published"
                )

            if announcement.status == "published":
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
        form = AnnouncementForm(instance=announcement, user=request.user)

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
@announcement_access(Role.MEMBER)
def announcements_list(request):
    publish_due_announcements()
    is_admin = is_officer_or_admin(request.user)

    # define filtering and search feature
    query = request.GET.get("q", "")
    category_slug = request.GET.get("category", "")
    tag = request.GET.get("tag", "").strip().casefold()[:32]
    status_filter = request.GET.get("status", "all")

    announcements = Announcement.objects.select_related(
        "author", "category", "committee"
    ).prefetch_related("attachments")


    if not is_admin:
        announcements = visible_announcements(
            request.user,
            request.announcement_role,
        ).select_related("author", "category", "committee").prefetch_related(
            "attachments",
        )
    elif status_filter != "all":
        announcements = announcements.filter(status=status_filter)

    if query:
        announcements = announcements.filter(
            Q(title__icontains=query)
            | Q(content__icontains=query)
        )

    if category_slug:
        announcements = announcements.filter(category__slug=category_slug)
    if tag:
        announcements = announcements.filter(tags__contains=[tag])

    announcements = list(announcements)
    if not is_admin:
        read_ids = set(
            AnnouncementReadReceipt.objects.filter(
                user=request.user,
                announcement__in=announcements,
            ).values_list("announcement_id", flat=True)
        )
    else:
        read_ids = set(
            AnnouncementReadReceipt.objects.filter(
                user=request.user,
                announcement__in=announcements,
            ).values_list("announcement_id", flat=True)
        )
    for item in announcements:
        item.is_read_by_user = item.pk in read_ids

    # display summary stats in admin view
    stats = {}
    if is_admin:
        stats = {
            "total": Announcement.objects.count(),
            "total_published": Announcement.objects.filter(
                status="published"
            ).count(),
            "active_drafts": Announcement.objects.filter(status="draft").count(),
            "scheduled_queue": Announcement.objects.filter(status="scheduled").count(),
            "audience_total": Profile.objects.filter(
                role__in=ROSTER_ROLES
            ).count(),
            "officer_total": Profile.objects.filter(
                role__in=[Role.OFFICER, Role.ADMIN]
            ).count(),
            "applicant_total": Profile.objects.filter(
                role=Role.APPLICANT
            ).count(),
        }

    categories = Category.objects.all()

    context = {
        "announcements": announcements,
        "categories": categories,
        "can_publish": is_admin,
        "stats": stats,
        "current_category": category_slug,
        "selected_tag": tag,
        "search_query": query,
        "status_filter": status_filter,
    }

    return render(
        request,
        "announcements/announcements_page.html",
        context,
    )

# === [ALL] DISPLAY ANNOUNCEMENT DETAIL
@announcement_access(Role.MEMBER)
def announcement_detail(request, pk):
    """Retrieve details about the announcement."""
    publish_due_announcements()
    announcement = get_object_or_404(
        Announcement.objects.select_related(
            "author", "category", "committee"
        ).prefetch_related("attachments", "comments__author"),
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
    if not is_admin and not can_receive_announcement(request.user, announcement):
        raise PermissionDenied("This announcement is not available to your audience.")

    is_read_by_user = AnnouncementReadReceipt.objects.filter(
        user=request.user,
        announcement=announcement
    ).exists()

    # related / recent notices in the same category
    related_announcements = Announcement.objects.filter(
        category=announcement.category,
        status="published"
    ).exclude(pk=announcement.pk).order_by("-published_at")[:3]
    if not is_admin:
        related_announcements = [
            item for item in related_announcements
            if can_receive_announcement(request.user, item)
        ]

    context = {
        "announcement": announcement,
        "can_publish": is_admin,
        "can_edit": is_admin and (
            request.user.is_superuser
            or get_role(request.user) == Role.ADMIN
            or announcement.author == request.user
        ),
        "is_read_by_user": is_read_by_user,
        "related_announcements": related_announcements,
        "comments": announcement.comments.all(),
        "comment_form": AnnouncementCommentForm(),
    }

    return render(request, "announcements/announcement_detail.html", context)


# === [DISPLAY] MARK AS READ TOGGLE
@announcement_access(Role.MEMBER)
@require_POST
def announcement_mark_read(request, pk):
    try:
        pk = ObjectId(str(pk))
    except (InvalidId, TypeError):
        raise Http404("Announcement not found.")
    announcement = get_object_or_404(
        Announcement,
        pk=pk,
    )
    if announcement.status != "published":
        raise PermissionDenied("Only published announcements can be marked read.")
    is_admin = is_officer_or_admin(request.user)
    if announcement.author_id == request.user.id:
        raise PermissionDenied("Authors cannot mark their own announcements as read.")
    if not is_admin and not can_receive_announcement(request.user, announcement):
        raise PermissionDenied(
            "This announcement is not available to your audience."
        )
    action = request.POST.get("action", "read")
    receipt = AnnouncementReadReceipt.objects.filter(
        user=request.user,
        announcement=announcement,
    ).first()
    if action == "unread" and receipt:
        receipt.delete()
        Announcement.objects.filter(
            pk=pk,
            read_count__gt=0,
        ).update(read_count=F("read_count") - 1)
    elif action != "unread" and receipt is None:
        AnnouncementReadReceipt.objects.create(
            user=request.user,
            announcement=announcement,
        )
        Announcement.objects.filter(pk=pk).update(read_count=F("read_count") + 1)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"is_read": action != "unread"})
    return redirect("announcements:list")


@announcement_access(Role.OFFICER)
def announcement_delete(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    if not is_officer_or_admin(request.user):
        raise PermissionDenied("You do not have permission to delete this announcement.")
    if request.user != announcement.author and get_role(request.user) != Role.ADMIN:
        raise PermissionDenied("Only the author or an admin can delete this announcement.")
    if request.method == "POST":
        announcement.delete()
        messages.success(request, "Announcement deleted.")
        return redirect("announcements:list")
    return render(
        request,
        "announcements/confirm_delete.html",
        {
            "object": announcement,
            "kind": "announcement",
            "cancel_url": "announcements:list",
        },
    )


@login_required
def announcement_comment_create(request, pk):
    """Create a comment when the announcement author enabled comments."""
    if request.method != "POST":
        return redirect("announcements:detail", pk=pk)

    announcement = get_object_or_404(Announcement, pk=pk, status="published")
    is_admin = is_officer_or_admin(request.user)
    if not is_admin and not can_receive_announcement(request.user, announcement):
        raise PermissionDenied("This announcement is not available to your audience.")
    if not announcement.comments_enabled:
        raise PermissionDenied("Comments are not enabled for this announcement.")

    form = AnnouncementCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.announcement = announcement
        comment.author = request.user
        comment.save()
        Announcement.objects.filter(pk=announcement.pk).update(
            comments_count=F("comments_count") + 1
        )
        return redirect("announcements:detail", pk=announcement.pk)

    messages.error(request, "Please enter a comment before posting.")
    return redirect("announcements:detail", pk=announcement.pk)

    return redirect("announcements:list")
