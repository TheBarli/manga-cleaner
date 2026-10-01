import unittest
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QColor
from PySide6.QtCore import Qt
from src.utils.history import HistoryManager

_app = QApplication.instance() or QApplication([])

class TestHistoryManager(unittest.TestCase):
    def setUp(self):
        self.history = HistoryManager(limit=5)

    def test_initial_state(self):
        self.assertFalse(self.history.can_undo())
        self.assertFalse(self.history.can_redo())

    def test_mask_undo_redo_roundtrip(self):
        # 1. Create a transparent mask
        mask1 = QImage(64, 64, QImage.Format_ARGB32)
        mask1.fill(Qt.transparent)
        self.history.push_mask_state(mask1)

        self.assertTrue(self.history.can_undo())
        self.assertFalse(self.history.can_redo())

        # 2. Mutate mask (draw red)
        mask2 = QImage(64, 64, QImage.Format_ARGB32)
        mask2.fill(QColor(255, 0, 0, 255))

        # 3. Undo should return state prior to mutation
        result = self.history.undo(None, mask2)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "mask")
        restored_mask = result["mask"]
        self.assertEqual(restored_mask.pixelColor(0, 0).alpha(), 0)
        self.assertTrue(self.history.can_redo())

        # 4. Redo should restore mask2
        redo_result = self.history.redo(None, restored_mask)
        self.assertIsNotNone(redo_result)
        self.assertEqual(redo_result["type"], "mask")
        redo_mask = redo_result["mask"]
        self.assertEqual(redo_mask.pixelColor(0, 0).red(), 255)
        self.assertFalse(self.history.can_redo())

    def test_image_action_undo_redo_roundtrip(self):
        img = np.zeros((32, 32, 3), dtype=np.uint8)
        patch = np.ones((10, 10, 3), dtype=np.uint8) * 150

        # Push legacy image patch
        self.history.push_image_action(0, 0, patch)
        self.assertTrue(self.history.can_undo())

        undo_res = self.history.undo(img, None)
        self.assertEqual(undo_res["type"], "image")
        self.assertTrue(np.array_equal(img[0:10, 0:10], patch))

        self.assertTrue(self.history.can_redo())
        redo_res = self.history.redo(img, None)
        self.assertEqual(redo_res["type"], "image")

    def test_stack_limit_eviction(self):
        limit = 3
        h = HistoryManager(limit=limit)
        for i in range(5):
            mask = QImage(16, 16, QImage.Format_ARGB32)
            mask.fill(QColor(i * 40, 0, 0, 255))
            h.push_mask_state(mask)

        # Undo count should be bounded by limit
        undo_count = 0
        current_mask = QImage(16, 16, QImage.Format_ARGB32)
        while h.can_undo():
            res = h.undo(None, current_mask)
            current_mask = res["mask"]
            undo_count += 1

        self.assertEqual(undo_count, limit)

    def test_clear_resets_history(self):
        mask = QImage(16, 16, QImage.Format_ARGB32)
        self.history.push_mask_state(mask)
        self.assertTrue(self.history.can_undo())

    def test_on_change_callback(self):
        call_count = 0
        def on_change():
            nonlocal call_count
            call_count += 1

        h = HistoryManager(limit=5, on_change=on_change)
        mask = QImage(16, 16, QImage.Format_ARGB32)
        h.push_mask_state(mask)
        self.assertEqual(call_count, 1)

        h.undo(None, mask)
        self.assertEqual(call_count, 2)

        h.redo(None, mask)
        self.assertEqual(call_count, 3)

        h.clear()
        self.assertEqual(call_count, 4)

if __name__ == '__main__':
    unittest.main()
