import shutil
import tempfile
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import override_settings

from announcements.models import Announcement, Category


User = get_user_model()


class AnnouncementTestDataMixin:
    @classmethod
    def setUpClass(cls):
        cls._test_media_root = tempfile.mkdtemp(
            prefix="announcements-tests-"
        )
        cls._media_override = override_settings(
            MEDIA_ROOT=cls._test_media_root
        )
        cls._media_override.enable()
        try:
            super().setUpClass()
        except Exception:
            cls._media_override.disable()
            shutil.rmtree(cls._test_media_root, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            super().tearDownClass()
        finally:
            cls._media_override.disable()
            shutil.rmtree(cls._test_media_root, ignore_errors=True)

    def make_user(self, username=None, **kwargs):
        username = f"{username or 'member'}-{uuid4().hex[:8]}"
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="test-password",
            **kwargs,
        )

    def make_category(self, name=None, slug=None):
        suffix = uuid4().hex[:8]
        name = name or f"General {suffix}"
        slug = slug or f"general-{suffix}"
        return Category.objects.create(name=name, slug=slug)

    def make_announcement(self, author=None, **kwargs):
        author = author or self.make_user()
        defaults = {
            "title": "A test announcement",
            "content": "Announcement content.",
            "author": author,
        }
        defaults.update(kwargs)
        defaults.setdefault("category", self.make_category())
        return Announcement.objects.create(**defaults)

    def make_officer(self, username=None):
        return self.make_user(username=username, is_staff=True)

    def login(self, user):
        self.client.force_login(user)
