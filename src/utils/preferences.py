from PySide6.QtCore import QSettings

class UserPrefs:
    """Manages persistent user preferences across sessions using Qt's QSettings."""
    _settings = None

    @classmethod
    def get_settings(cls) -> QSettings:
        if cls._settings is None:
            cls._settings = QSettings("MangaCleaner", "Studio")
        return cls._settings

    @classmethod
    def save(cls, key: str, value):
        """Saves a key-value preference."""
        cls.get_settings().setValue(key, value)

    @classmethod
    def load(cls, key: str, default=None, value_type=None, type=None):
        """Loads a preference value with optional default and type conversion."""
        target_type = value_type if value_type is not None else type
        settings = cls.get_settings()
        if target_type is not None:
            return settings.value(key, default, type=target_type)
        return settings.value(key, default)

    @classmethod
    def sync(cls):
        """Flushes preferences to persistent storage."""
        if cls._settings is not None:
            cls._settings.sync()

    @classmethod
    def clear(cls):
        """Clears all stored preferences."""
        cls.get_settings().clear()
