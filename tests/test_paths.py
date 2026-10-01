import unittest
import os
from src.utils.paths import Paths

class TestPaths(unittest.TestCase):
    def test_paths_initialization(self):
        Paths.initialize()
        self.assertTrue(os.path.exists(Paths.MODELS))
        self.assertTrue(os.path.exists(Paths.LOGS))
        self.assertTrue(os.path.exists(Paths.CACHE))
        self.assertTrue(os.path.exists(Paths.PROCESSED))

    def test_get_model_path(self):
        model_name = "lama_fp16.onnx"
        model_path = Paths.get_model(model_name)
        self.assertEqual(model_path, os.path.join(Paths.MODELS, model_name))

if __name__ == '__main__':
    unittest.main()
