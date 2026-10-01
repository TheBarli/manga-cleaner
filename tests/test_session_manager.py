import unittest
from unittest.mock import MagicMock
from collections import OrderedDict
from src.frontend.controllers.session_manager import SessionManager, PageState

class TestSessionManagerLRU(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.current_img_path = None
        self.mock_window.pipeline_controller.get_locked_paths.return_value = set()
        self.sm = SessionManager(self.mock_window)
        self.sm.max_cached_sessions = 3

    def test_lru_eviction_under_limit(self):
        for i in range(3):
            self.sm.image_sessions[f"file_{i}.png"] = {"data": i}
        self.sm._ensure_session_limit()
        self.assertEqual(len(self.sm.image_sessions), 3)

    def test_lru_evicts_oldest_first(self):
        for i in range(4):
            self.sm.image_sessions[f"file_{i}.png"] = {"data": i}
        self.sm._ensure_session_limit()

        # Should evict file_0.png
        self.assertEqual(len(self.sm.image_sessions), 3)
        self.assertNotIn("file_0.png", self.sm.image_sessions)
        self.assertIn("file_1.png", self.sm.image_sessions)
        self.assertIn("file_2.png", self.sm.image_sessions)
        self.assertIn("file_3.png", self.sm.image_sessions)

    def test_lru_protects_active_image(self):
        # file_0 is the oldest, but it's active in canvas
        self.sm.image_sessions["file_0.png"] = {"data": 0}
        self.sm.image_sessions["file_1.png"] = {"data": 1}
        self.sm.image_sessions["file_2.png"] = {"data": 2}
        self.sm.image_sessions["file_3.png"] = {"data": 3}
        self.sm.current_img_path = "file_0.png"

        self.sm._ensure_session_limit()

        # file_0 must be preserved; file_1 was next oldest and should be evicted
        self.assertEqual(len(self.sm.image_sessions), 3)
        self.assertIn("file_0.png", self.sm.image_sessions)
        self.assertNotIn("file_1.png", self.sm.image_sessions)

    def test_lru_protects_in_flight_tasks(self):
        self.sm.image_sessions["file_0.png"] = {"data": 0}
        self.sm.image_sessions["file_1.png"] = {"data": 1}
        self.sm.image_sessions["file_2.png"] = {"data": 2}
        self.sm.image_sessions["file_3.png"] = {"data": 3}
        # file_0 is locked/in-flight in the worker pipeline
        self.mock_window.pipeline_controller.get_locked_paths.return_value = {"file_0.png"}

        self.sm._ensure_session_limit()

        self.assertEqual(len(self.sm.image_sessions), 3)
        self.assertIn("file_0.png", self.sm.image_sessions)
        self.assertNotIn("file_1.png", self.sm.image_sessions)

if __name__ == '__main__':
    unittest.main()
