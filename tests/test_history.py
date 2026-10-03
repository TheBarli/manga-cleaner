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
        self.history.clear()
        self.assertFalse(self.history.can_undo())
        self.assertFalse(self.history.can_redo())

    def test_clean_undo_overlapping_tiles_restores_original(self):
        """Regression test for overlapping-tile undo pixel restoration (R2-03a)."""
        orig = np.zeros((10, 20, 3), np.uint8)
        output = orig.copy()
        history = []
        # tile A covers x 0..12, tile B covers x 8..20 (overlap 8..12)
        for (x1, x2, val) in [(0, 12, 100), (8, 20, 200)]:
            history.append((x1, 0, output[:, x1:x2].copy()))
            output[:, x1:x2] = val
        h = HistoryManager(10)
        h.push_image_clean(history, output)
        img = output.copy()
        h.undo(img, None)
        self.assertTrue(np.array_equal(img, orig))
        self.assertEqual(len(np.unique(img[:, 8:12])), 1)
        self.assertEqual(img[0, 10, 0], 0)

    def test_redo_clean_preserves_remaining_redo_stack(self):
        """Regression test for redo stack retention when redoing an AI clean (R2-03b)."""
        from src.frontend.canvas import MangaCanvas
        c = MangaCanvas()
        hist = HistoryManager(10)
        c.mask_changed.connect(lambda: hist.push_mask_state(c.mask))
        base = np.zeros((16, 16, 3), np.uint8)
        c.set_image(base.copy(), orig_img=base.copy())

        # Step 1: AI clean
        patches = [(0, 0, base[0:8, 0:8].copy())]
        res_img = base.copy()
        res_img[0:8, 0:8] = 255
        hist.push_image_clean(patches, res_img, saved_mask=c.mask.copy())
        c.set_image(res_img)

        # Step 2: Mask stroke
        c.mask_changed.emit()
        self.assertEqual(len(hist.undo_stack), 2)

        # Undo both operations
        hist.undo(c.cv_img, c.mask)
        hist.undo(c.cv_img, c.mask)
        self.assertEqual(len(hist.redo_stack), 2)

        # Redo the clean using reset_mask (as implemented in PipelineController)
        r = hist.redo(c.cv_img, c.mask)
        c.set_image(r["img"])
        if r.get("clear_mask"):
            c.reset_mask()

        # Redo stack must still retain the mask stroke action
        self.assertEqual(len(hist.redo_stack), 1)

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
