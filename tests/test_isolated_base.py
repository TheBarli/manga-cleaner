import os
import sys
import unittest
import tempfile
from unittest import mock
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from src.utils.paths import Paths
from src.utils.config import Config
from src.utils.preferences import UserPrefs

class IsolatedTestCase(unittest.TestCase):
    """Hermetic test base fixture that protects real user QSettings and project directories."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        super().setUp()
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = self._tmp_dir.name

        # Sandbox Cache and Processed directories
        self.fake_cache = os.path.join(self.tmp_path, "cache")
        self.fake_processed = os.path.join(self.tmp_path, "processed")
        os.makedirs(self.fake_cache, exist_ok=True)
        os.makedirs(self.fake_processed, exist_ok=True)

        self._patch_cache = mock.patch.object(Paths, "CACHE", self.fake_cache)
        self._patch_proc = mock.patch.object(Paths, "PROCESSED", self.fake_processed)
        self._patch_cache.start()
        self._patch_proc.start()

        # Sandbox batch id file
        self._orig_id_file = Config._ID_FILE
        Config._ID_FILE = os.path.join(self.fake_cache, "batch_id.json")

        # Sandbox QSettings to an isolated temp INI file
        self._orig_settings = UserPrefs._settings
        self.fake_ini = os.path.join(self.tmp_path, "test_prefs.ini")
        UserPrefs._settings = QSettings(self.fake_ini, QSettings.IniFormat)

    def tearDown(self):
        Config._ID_FILE = self._orig_id_file
        UserPrefs._settings = self._orig_settings
        self._patch_cache.stop()
        self._patch_proc.stop()
        self._tmp_dir.cleanup()
        super().tearDown()
