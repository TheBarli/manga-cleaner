import os
import sys
from PySide6.QtCore import QStandardPaths

#/////////////////////////////////#
#      FILESYSTEM ARCHITECT       #
#/////////////////////////////////#

class Paths:
    BASE_DIR = ""
    BUNDLE_DIR = ""
    DATA_DIR = ""
    MODELS = ""
    LOGS = ""
    CACHE = ""
    PROCESSED = ""

    @classmethod
    def recompute(cls):
        """Calculates filesystem paths based on environment (frozen vs development)."""
        if getattr(sys, 'frozen', False):
            cls.BASE_DIR = os.path.dirname(sys.executable)
            cls.BUNDLE_DIR = getattr(sys, '_MEIPASS', cls.BASE_DIR)
            app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
            if app_data and not app_data.endswith("MangaCleaner"):
                cls.DATA_DIR = os.path.join(app_data, "MangaCleaner")
            else:
                cls.DATA_DIR = app_data if app_data else os.path.join(cls.BASE_DIR, "data")
            cls.LOGS = os.path.join(cls.DATA_DIR, "logs")
            cls.CACHE = os.path.join(cls.DATA_DIR, "cache")
            pics = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
            cls.PROCESSED = os.path.join(pics if pics else cls.DATA_DIR, "MangaCleaner")
        else:
            cls.BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            cls.BUNDLE_DIR = cls.BASE_DIR
            cls.DATA_DIR = cls.BASE_DIR
            cls.LOGS = os.path.join(cls.BASE_DIR, "logs")
            cls.CACHE = os.path.join(cls.BASE_DIR, "cache")
            cls.PROCESSED = os.path.join(cls.BASE_DIR, "processed")

        cls.MODELS = os.path.join(cls.BASE_DIR, "models")

    @staticmethod
    def initialize():
        for p in [Paths.MODELS, Paths.LOGS, Paths.CACHE, Paths.PROCESSED]:
            try:
                os.makedirs(p, exist_ok=True)
            except Exception:
                if not os.path.exists(p):
                    raise

    @staticmethod
    def get_model(name):
        return os.path.join(Paths.MODELS, name)

# Initialize paths on module load
Paths.recompute()
