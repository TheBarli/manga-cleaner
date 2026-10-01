import unittest
import os
import shutil
import numpy as np
from src.backend.batch_engine import BatchEngine

class TestBatchEngine(unittest.TestCase):
    def setUp(self):
        self.engine = BatchEngine()
        self.created_dirs = []

    def tearDown(self):
        for d in self.created_dirs:
            if os.path.exists(d):
                try:
                    shutil.rmtree(d)
                except Exception:
                    pass

    def test_batch_lifecycle(self):
        fake_files = [
            os.path.abspath("page_01.png"),
            os.path.abspath("page_02.png"),
            os.path.abspath("page_03.png")
        ]

        out_dir = self.engine.initialize_batch(fake_files, "png")
        self.created_dirs.append(out_dir)

        self.assertTrue(os.path.exists(out_dir))
        self.assertEqual(len(self.engine.files), 3)
        self.assertEqual(self.engine.current_index, 0)

        # First file
        next_file = self.engine.get_next()
        self.assertEqual(next_file, fake_files[0])

        dummy_img = np.zeros((20, 20, 3), dtype=np.uint8)
        is_last = self.engine.save_current(dummy_img)
        self.assertFalse(is_last)
        self.assertEqual(self.engine.current_index, 1)

        expected_saved = os.path.join(out_dir, "page_01_cleaned.png")
        self.assertTrue(os.path.exists(expected_saved))

        # Second file
        self.assertEqual(self.engine.get_next(), fake_files[1])
        is_last = self.engine.save_current(dummy_img)
        self.assertFalse(is_last)

        # Third and final file
        self.assertEqual(self.engine.get_next(), fake_files[2])
        is_last = self.engine.save_current(dummy_img)
        self.assertTrue(is_last)

    def test_empty_batch(self):
        self.engine.initialize_batch([], "png")
        self.assertIsNone(self.engine.get_next())

if __name__ == '__main__':
    unittest.main()
