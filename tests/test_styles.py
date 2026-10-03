import unittest
import os
import sys
from PySide6.QtWidgets import QApplication
from tests.test_isolated_base import IsolatedTestCase
from src.utils.paths import Paths

class TestStyles(IsolatedTestCase):

    def test_qss_files_exist_and_contain_selectors(self):
        dark_qss_path = os.path.join(Paths.BASE_DIR, "src", "frontend", "styles.qss")
        light_qss_path = os.path.join(Paths.BASE_DIR, "src", "frontend", "styles_light.qss")

        self.assertTrue(os.path.exists(dark_qss_path))
        self.assertTrue(os.path.exists(light_qss_path))

        expected_selectors = [
            "#AssetsHeading",
            "#ToolGroupHeading",
            "#ModeLabel",
            "#QueueLabel",
            "#SliderValueLabel",
            "#HardwareMonitorLabel",
            "#StatusFileLabel",
            "#StatusToolLabel",
            "#StatusHistoryLabel",
            "#StatusCoordLabel",
            "#StatusDimLabel",
            "#StatusZoomButton"
        ]

        with open(dark_qss_path, "r", encoding="utf-8") as f:
            dark_content = f.read()
        for sel in expected_selectors:
            self.assertIn(sel, dark_content, f"Dark QSS missing selector {sel}")

        with open(light_qss_path, "r", encoding="utf-8") as f:
            light_content = f.read()
        for sel in expected_selectors:
            self.assertIn(sel, light_content, f"Light QSS missing selector {sel}")

    def test_main_window_object_names(self):
        from src.frontend.main_window import MainWindow
        win = MainWindow()
        self.assertEqual(win.mode_lbl.objectName(), "ModeLabel")
        self.assertEqual(win.queue_lbl.objectName(), "QueueLabel")
        self.assertEqual(win.status_file_lbl.objectName(), "StatusFileLabel")
        self.assertEqual(win.status_tool_lbl.objectName(), "StatusToolLabel")
        self.assertEqual(win.status_history_lbl.objectName(), "StatusHistoryLabel")
        self.assertEqual(win.status_coord_lbl.objectName(), "StatusCoordLabel")
        self.assertEqual(win.status_dim_lbl.objectName(), "StatusDimLabel")
        self.assertEqual(win.status_zoom_btn.objectName(), "StatusZoomButton")
        win.close()

if __name__ == '__main__':
    unittest.main()
