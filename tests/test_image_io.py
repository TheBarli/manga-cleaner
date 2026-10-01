import unittest
import os
import tempfile
import numpy as np
from src.utils.image_io import safe_imwrite, safe_imread

class TestImageIO(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.gettempdir()
        self.test_files = []

    def tearDown(self):
        for path in self.test_files:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def test_unicode_path_write_read(self):
        unicode_name = "日本語_マンガ_テスト_01.png"
        path = os.path.join(self.temp_dir, unicode_name)
        self.test_files.append(path)

        img = np.zeros((50, 50, 3), dtype=np.uint8)
        img[10:30, 10:30] = [255, 128, 64]

        success = safe_imwrite(path, img)
        self.assertTrue(success)
        self.assertTrue(os.path.exists(path))

        loaded = safe_imread(path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.shape, img.shape)
        self.assertTrue(np.array_equal(loaded, img))

    def test_alpha_channel_write_read(self):
        alpha_name = "test_transparency_alpha.png"
        path = os.path.join(self.temp_dir, alpha_name)
        self.test_files.append(path)

        img_rgba = np.zeros((40, 40, 4), dtype=np.uint8)
        img_rgba[:, :, 3] = 180  # Semi-transparent alpha

        success = safe_imwrite(path, img_rgba)
        self.assertTrue(success)

        loaded = safe_imread(path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.shape[2], 4)
        self.assertEqual(loaded[0, 0, 3], 180)

    def test_nonexistent_read(self):
        result = safe_imread(os.path.join(self.temp_dir, "non_existent_file_12345.png"))
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
