import unittest
from src.utils.config import Config

class TestConfig(unittest.TestCase):
    def test_batch_id_format(self):
        batch_id = Config.get_next_batch_id()
        self.assertTrue(batch_id.startswith("batch_"))
        self.assertEqual(len(batch_id), 11)  # batch_ + 5 digits (e.g. batch_00001)

    def test_batch_id_sequential(self):
        id1 = Config.get_next_batch_id()
        id2 = Config.get_next_batch_id()
        num1 = int(id1.split("_")[1])
        num2 = int(id2.split("_")[1])
        self.assertEqual(num2, num1 + 1)

    def test_constants_defined(self):
        self.assertIsInstance(Config.MAX_HISTORY, int)
        self.assertGreater(Config.MAX_HISTORY, 0)
        self.assertIsInstance(Config.MAX_CACHED_SESSIONS, int)
        self.assertGreater(Config.MAX_CACHED_SESSIONS, 0)
        self.assertTrue(hasattr(Config, "COLOR_BG_BASE"))
        self.assertTrue(hasattr(Config, "COLOR_ACCENT"))
        self.assertTrue(hasattr(Config, "COLOR_TEXT_PRIMARY"))

if __name__ == '__main__':
    unittest.main()
