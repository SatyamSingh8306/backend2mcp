"""Pytest configuration for backend2mcp tests."""

import os
import sys

# Ensure python directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


class _SettingsProxy:
    """Minimal pytest-django compatible ``settings`` fixture shim.

    The test-suite configures Django in ``setup_django`` already, so calling
    ``configure()`` again would raise.  This proxy keeps the fixture API that
    the tests use without requiring the optional pytest-django dependency.
    """

    def configure(self, **kwargs):
        from django.conf import settings

        if not settings.configured:
            settings.configure(**kwargs)
            import django

            django.setup()

    def __getattr__(self, name):
        from django.conf import settings

        return getattr(settings, name)


@pytest.fixture
def settings():
    """Return a proxy around ``django.conf.settings``."""
    return _SettingsProxy()


@pytest.fixture(scope="session", autouse=True)
def setup_django():
    """Set up Django for tests that need it."""
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            DEBUG=True,
            SECRET_KEY="test-secret-key-for-testing",
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        )
        django.setup()