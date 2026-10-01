import unittest
from src.utils.preferences import UserPrefs

class TestUserPrefs(unittest.TestCase):
    def setUp(self):
        UserPrefs.clear()

    def tearDown(self):
        UserPrefs.clear()

    def test_save_load_int(self):
        UserPrefs.save("test_int", 85)
        val = UserPrefs.load("test_int", 0, type=int)
        self.assertEqual(val, 85)

    def test_save_load_str(self):
        UserPrefs.save("test_dir", "/path/to/folder")
        val = UserPrefs.load("test_dir", "")
        self.assertEqual(val, "/path/to/folder")

    def test_load_default_when_missing(self):
        val = UserPrefs.load("non_existent_key_xyz", 42, type=int)
        self.assertEqual(val, 42)

    def test_clear(self):
        UserPrefs.save("key_to_clear", "sample")
        UserPrefs.clear()
        val = UserPrefs.load("key_to_clear", "default")
        self.assertEqual(val, "default")

if __name__ == '__main__':
    unittest.main()
