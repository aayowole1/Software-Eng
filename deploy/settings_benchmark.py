"""Opt-in local benchmark settings; never used by normal startup/deployment."""
import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from orgflow_project.settings import *  # noqa: F403,E402
from django.core.exceptions import ImproperlyConfigured

if not DATABASES["default"]["NAME"].startswith("orgflow_perf_"):
    raise ImproperlyConfigured("Benchmark settings require a separate orgflow_perf_* database.")

DEBUG = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
