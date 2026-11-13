"""
@brief      Define the models used for announcements.

@citation   Google Stitch was used to help with designing the UI and connecting with Django.
"""

# === IMPORTS
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django_mongodb_backend.fields import ArrayField

from accounts.models import ROSTER_ROLES
from committees.models import Committee

# === CONFIG
User = get_user_model()

# === [CLASS] CATEGORY
class Category(models.Model):
    """Manage the announcement categories."""
    name = models.CharField(max_length=64)
    slug = models.SlugField(unique=True)
    committee = models.ForeignKey(
        Committee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcement_categories",
    )

    class Meta:
        """Define the category metadata."""
        verbose_name_plural = "Categories"

    # === DUNDER METHODS
    def __str__(self) -> str:
        return self.name


class Resource(models.Model):
    """Define a member-accessible resource library item."""
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, max_length=5000)
    category = models.CharField(max_length=64, blank=True)
    tags = ArrayField(models.CharField(max_length=32), max_size=10, default=list, blank=True)
    file = models.FileField(upload_to="resources/%Y/%m/", blank=True)
    url = models.URLField(max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
    )

    class Meta:
        ordering = ["title", "id"]

    def __str__(self) -> str:
        return self.title


# === [CLASS] ANNOUNCEMENT
class Announcement(models.Model):
    """Define a single announcement object."""
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]
    title = models.CharField(max_length=255)
    content = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="published",
    )
    is_pinned = models.BooleanField(default=False)
    is_urgent = models.BooleanField(default=False)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name="announcements",
    )
    committee = models.ForeignKey(
        Committee,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="announcements",
    )
    tags = ArrayField(models.CharField(max_length=32), max_size=10, default=list, blank=True)

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="announcements",
    )
    author_role = models.CharField(
        max_length=100,
        default="Officer",
    )

    published_at = models.DateTimeField(
        default=timezone.now
    )
    scheduled_for = models.DateTimeField(
        null=True, blank=True
    )
    comments_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        auto_now=True
    )

    # optional meeting metadata
    meeting_location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    meeting_virtual_url = models.URLField(
        blank=True, null=True
    )

    # telemetry and engagement
    read_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = [
            "-is_pinned",
            "-published_at",
        ]


    # === DUNDER METHODS
    def __str__(self) -> str:
        return self.title

    # === PROPERTIES
    @property
    def audience_count(self) -> int:
        """Return the current number of users who can receive this post."""
        if self.committee_id:
            return self.committee.members.filter(
                user__profile__role__in=ROSTER_ROLES
            ).exclude(user_id=self.author_id).count()
        return User.objects.filter(
            profile__role__in=ROSTER_ROLES
        ).exclude(pk=self.author_id).count()

    @property
    def read_percentage(self) -> int:
        """Return the current read percentage for the announcement audience."""
        audience_count = self.audience_count
        if audience_count > 0:
            return min(
                100,
                int(((self.read_count or 0) / audience_count) * 100)
            )

        return 0


# === [CLASS] ANNOUNCEMENT ATTACHMENT
class AnnouncementAttachment(models.Model):
    """Manage an announcement's attachment."""
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(
        upload_to="announcements/%Y/%m/"
    )
    name = models.CharField(max_length=255)
    size_label = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g., 2.4 MB",
    )

    # === DUNDER METHODS
    def __str__(self) -> str:
        return self.name


# === [CLASS] ANNOUNCEMENT READ RECEIPT
class AnnouncementReadReceipt(models.Model):
    """Manage the announcement's read receipt."""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE
    )
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name="read_receipts",
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Define the read receipt metadata."""
        # define the unique key pair
        unique_together = ("user", "announcement")


class AnnouncementComment(models.Model):
    """Store a comment posted on an announcement."""
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="announcement_comments",
    )
    content = models.TextField(max_length=2000)
    moderation_status = models.CharField(
        max_length=16,
        choices=[("visible", "Visible"), ("flagged", "Flagged")],
        default="visible",
    )
    moderation_reason = models.CharField(max_length=500, blank=True)
    moderation_provider = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Comment by {self.author} on {self.announcement}"


class AnnouncementCommentAudit(models.Model):
    """Immutable history for comment creation, moderation, and deletion."""

    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name="comment_audits",
    )
    comment_id = models.CharField(max_length=32)
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=16)
    content = models.TextField(max_length=2000)
    detail = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
