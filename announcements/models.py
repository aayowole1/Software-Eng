"""
@brief      Define the models used for announcements.

@citation   Google Stitch was used to help with designing the UI and connecting with Django.
"""

# === IMPORTS
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django_mongodb_backend.fields import ArrayField


# === CONFIG
User = get_user_model()

# === [CLASS] CATEGORY
class Category(models.Model):
    """Manage the announcement categories."""
    name = models.CharField(max_length=64)
    slug = models.SlugField(unique=True)

    class Meta:
        """Define the category metadata."""
        verbose_name_plural = "Categories"

    # === DUNDER METHODS
    def __str__(self) -> str:
        return self.name


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
        "committees.Committee",
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
    target_reach = models.PositiveIntegerField(default=165)
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
    def read_percentage(self) -> int:
        """Return read percentage of announcement post."""
        if self.target_reach > 0:
            return min(
                100,
                int((self.read_count / self.target_reach) * 100)
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


class Resource(models.Model):
    """A shared organization file or external HTTP(S) link."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, max_length=5000)
    category = models.CharField(max_length=64, blank=True)
    tags = ArrayField(models.CharField(max_length=32), max_size=10, default=list, blank=True)
    file = models.FileField(upload_to="resources/%Y/%m/", blank=True)
    url = models.URLField(max_length=2000, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title", "id"]

    def __str__(self):
        return self.title
