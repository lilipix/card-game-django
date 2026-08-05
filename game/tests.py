from django.conf import settings
from django.test import SimpleTestCase


class SettingsSmokeTests(SimpleTestCase):
    def test_static_files_are_configured(self):
        self.assertEqual(settings.STATIC_URL, "/static/")
        self.assertEqual(settings.STATIC_ROOT.name, "staticfiles")
