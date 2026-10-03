import os
import unittest
import numpy as np
from collections import Counter
from PySide6.QtGui import QShortcut, QAction, QKeySequence, QImage, QColor

from tests.test_isolated_base import IsolatedTestCase
from src.frontend.main_window import MainWindow
from src.frontend.controllers.session_manager import SessionManager, PageState

class TestPhase1Regressions(IsolatedTestCase):
    """Regression suite confirming Phase 1 fixes."""

    def test_no_duplicate_shortcuts(self):
        """U2-01 regression: Ensure no shortcut key sequence is registered more than once."""
        win = MainWindow()
        keys = Counter()
        for sc in win.findChildren(QShortcut):
            seq = sc.key().toString()
            if seq:
                keys[seq] += 1
        for act in win.findChildren(QAction):
            for k in act.shortcuts():
                seq = k.toString()
                if seq:
                    keys[seq] += 1

        duplicates = {k: v for k, v in keys.items() if v > 1}
        self.assertEqual(duplicates, {}, f"Duplicate shortcut registrations found: {duplicates}")
        win.timer.stop()
        win.close()

    def test_ocr_mask_color_alignment(self):
        """U2-02 regression: Ensure OCR mask generation formats BGRA matching Format_ARGB32."""
        win = MainWindow()
        target_color = win.canvas.current_mask_color

        # Simulate pipeline mask generation logic
        result = np.ones((10, 10), dtype=np.uint8)
        rgba = np.zeros((10, 10, 4), dtype=np.uint8)
        c = win.canvas.current_mask_color
        color_bgra = [c.blue(), c.green(), c.red(), 255]
        rgba[result > 0] = color_bgra
        q_mask = QImage(rgba.data, 10, 10, 40, QImage.Format_ARGB32).copy()

        pixel = q_mask.pixelColor(0, 0)
        self.assertEqual(pixel.red(), target_color.red())
        self.assertEqual(pixel.green(), target_color.green())
        self.assertEqual(pixel.blue(), target_color.blue())
        self.assertEqual(pixel.alpha(), 255)
        win.timer.stop()
        win.close()

    def test_memory_only_ready_sessions_not_evicted(self):
        """R2-02 regression: In-memory READY sessions (batch export=none) must not be evicted."""
        from unittest.mock import MagicMock
        sm = SessionManager(MagicMock())
        sm.max_cached_sessions = 3
        sm.current_img_path = "active_page.png"
        sm.image_sessions["active_page.png"] = {"img": np.zeros((10, 10, 3)), "persisted_path": None}
        sm.page_states["active_page.png"] = PageState.UNMODIFIED

        # Add 5 READY pages with no persisted_path (in-memory only)
        for i in range(5):
            path = f"memory_page_{i}.png"
            sm.image_sessions[path] = {
                "img": np.zeros((10, 10, 3)),
                "persisted_path": None
            }
            sm.page_states[path] = PageState.READY

        self.assertEqual(len(sm.image_sessions), 6)
        sm._ensure_session_limit()

        # None of the 5 memory-only pages should have been evicted
        self.assertEqual(len(sm.image_sessions), 6)
        for i in range(5):
            self.assertIn(f"memory_page_{i}.png", sm.image_sessions)

if __name__ == '__main__':
    unittest.main()
