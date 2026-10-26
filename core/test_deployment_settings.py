"""Fail-closed release configuration, checked in fresh interpreter processes."""
import json
import os
from pathlib import Path
import subprocess
import sys
from django.test import SimpleTestCase


class ProductionSettingsTests(SimpleTestCase):
    def load(self, changes=None):
        # No developer/provider credentials inherited by these subprocesses.
        env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP') if key in os.environ}
        env.update({
            'DJANGO_SECRET_KEY': 'configuration-test-only-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789-abcdefghijk',
            'DJANGO_ALLOWED_HOSTS': 'demo.example.invalid,localhost',
            'MONGODB_URI': 'mongodb://127.0.0.1:27029',
            'MONGODB_NAME': 'orgflow_deployment_config_test',
            'DJANGO_EMAIL_POLICY': 'disabled',
        })
        for key, value in (changes or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        code = '''import json
from orgflow_project import settings_production as s
print(json.dumps({"debug":s.DEBUG,"secure_session":s.SESSION_COOKIE_SECURE,"secure_csrf":s.CSRF_COOKIE_SECURE,"redirect":s.SECURE_SSL_REDIRECT,"proxy":s.SECURE_PROXY_SSL_HEADER,"email":s.EMAIL_BACKEND,"hosts":s.ALLOWED_HOSTS}))'''
        return subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1], env=env, text=True, capture_output=True, timeout=15)

    def rejected(self, changes):
        result = self.load(changes)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ImproperlyConfigured', result.stderr)

    def test_secure_defaults_and_explicit_disabled_email(self):
        result = self.load()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data['debug'])
        self.assertTrue(all(data[key] for key in ('secure_session', 'secure_csrf', 'redirect')))
        self.assertIsNone(data['proxy'])
        self.assertEqual(data['email'], 'django.core.mail.backends.dummy.EmailBackend')

    def test_missing_secret_rejected(self):
        self.rejected({'DJANGO_SECRET_KEY': None})

    def test_weak_secret_rejected(self):
        self.rejected({'DJANGO_SECRET_KEY': 'x' * 64})

    def test_missing_hosts_rejected(self):
        self.rejected({'DJANGO_ALLOWED_HOSTS': None})

    def test_wildcard_hosts_rejected(self):
        self.rejected({'DJANGO_ALLOWED_HOSTS': '*'})

    def test_database_uri_required(self):
        self.rejected({'MONGODB_URI': None})

    def test_database_name_required(self):
        self.rejected({'MONGODB_NAME': None})

    def test_plaintext_csrf_origin_rejected(self):
        self.rejected({'DJANGO_CSRF_TRUSTED_ORIGINS': 'http://demo.example.invalid'})

    def test_smtp_requires_explicit_host_and_sender(self):
        self.rejected({'DJANGO_EMAIL_POLICY': 'smtp'})

    def test_plaintext_smtp_requires_test_opt_in(self):
        self.rejected({'DJANGO_EMAIL_POLICY': 'smtp', 'EMAIL_HOST': 'smtp.example.invalid', 'DEFAULT_FROM_EMAIL': 'OrgFlow <smoke@example.invalid>', 'EMAIL_USE_TLS': 'false'})

    def test_trusted_proxy_requires_explicit_opt_in(self):
        result = self.load({'DJANGO_TRUST_PROXY_HEADERS': 'true'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['proxy'], ['HTTP_X_FORWARDED_PROTO', 'https'])
