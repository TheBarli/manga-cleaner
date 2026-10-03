import os
import sys
import unittest
from unittest import mock
import numpy as np
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox

from tests.test_isolated_base import IsolatedTestCase
from src.frontend.main_window import MainWindow
from src.frontend.controllers.session_manager import PageState
from src.utils.paths import Paths
from src.backend.workers import get_pool, reset_pool, shutdown_pool

class TestPipelineRegressions(IsolatedTestCase):
    """Regression test suite for Phase 2 stability, crash resilience, and pipeline robustness."""

    def test_process_pool_reset_on_crash(self):
        """Task 1 / R2-04: reset_pool terminates previous executor and recreates it."""
        try:
            pool1 = get_pool()
            self.assertIsNotNone(pool1)
            pool2 = reset_pool()
            self.assertIsNotNone(pool2)
            self.assertIsNot(pool1, pool2)
        finally:
            shutdown_pool()

    def test_pipeline_recovers_when_session_deleted(self):
        """Task 2 / R2-04, 02 #3: on_task_finished safely ignores closed sessions without raising KeyError."""
        win = MainWindow()
        try:
            pc = win.pipeline_controller
            # Simulate a worker running on an image that was removed
            dummy_worker = mock.MagicMock()
            dummy_worker.task = "clean"
            dummy_worker.source_path = "C:/fake/path/deleted_image.png"
            pc.worker = dummy_worker
            pc.worker_thread = mock.MagicMock(spec=QThread)

            # Ensure deleted_image.png is NOT in image_sessions
            win.image_sessions.pop("C:/fake/path/deleted_image.png", None)
            win.current_img_path = "C:/fake/path/different_active.png"

            # Should not raise KeyError and should cleanly call stop_thread
            result = np.zeros((10, 10, 3), dtype=np.uint8)
            pc.on_task_finished(result, [])
            self.assertIsNone(pc.worker_thread)
        finally:
            win.timer.stop()
            win.close()

    def test_queue_counter_never_negative(self):
        """Task 4 / U2-04: Queue pending label never displays negative numbers."""
        win = MainWindow()
        try:
            pc = win.pipeline_controller
            pc.total_lama_tasks = 0
            pc.completed_lama_tasks = 1
            pc._update_queue_ui()
            self.assertIn("Processing / Queued: 0", win.queue_lbl.text())

            # Also verify clean completion does not increment past total
            dummy_worker = mock.MagicMock()
            dummy_worker.task = "clean"
            dummy_worker.source_path = win.current_img_path
            pc.worker = dummy_worker
            pc.completed_lama_tasks = 0
            pc.total_lama_tasks = 0
            pc.on_task_finished(np.zeros((10, 10, 3), dtype=np.uint8), [])
            self.assertEqual(pc.completed_lama_tasks, 0)
        finally:
            win.timer.stop()
            win.close()

    def test_batch_skips_clean_on_empty_ocr_mask(self):
        """Task 4 / R2-11: Empty OCR detection mask bypasses LaMa clean and saves directly."""
        win = MainWindow()
        try:
            bc = win.batch_controller
            bc.is_batching = True
            bc.batch_engine.files = ["C:/fake/page1.png"]
            bc.batch_engine.current_index = 0
            bc.batch_engine.export_format = "none"

            # Setup session with an empty mask
            path = "C:/fake/page1.png"
            win.image_sessions[path] = {
                "img": np.zeros((10, 10, 3), dtype=np.uint8),
                "orig": np.zeros((10, 10, 3), dtype=np.uint8),
                "mask": QImage(10, 10, QImage.Format_ARGB32),
                "history": mock.MagicMock()
            }
            win.image_sessions[path]["mask"].fill(Qt.transparent)
            win.pipeline_controller.total_lama_tasks = 1

            with mock.patch.object(win.pipeline_controller, "enqueue_task") as mock_enqueue:
                with mock.patch.object(bc.batch_engine, "save_current", return_value=True):
                    bc.handle_task_finished("ocr", path, is_active=False)
                    # Verify clean task was NOT enqueued
                    for call_args in mock_enqueue.call_args_list:
                        self.assertNotEqual(call_args[0][0], "clean")
                    self.assertEqual(win.page_states[path], PageState.READY)
        finally:
            win.timer.stop()
            win.close()

    def test_paths_frozen_mode(self):
        """Task 3 / R2-07: Paths in frozen mode use standard writable app data directories."""
        with mock.patch.object(sys, "frozen", True, create=True):
            Paths.recompute()
            try:
                self.assertIn("MangaCleaner", Paths.DATA_DIR)
                self.assertTrue(Paths.LOGS.startswith(Paths.DATA_DIR))
                self.assertTrue(Paths.CACHE.startswith(Paths.DATA_DIR))
                self.assertIn("MangaCleaner", Paths.PROCESSED)
            finally:
                pass
        # Restore non-frozen paths
        Paths.recompute()
        self.assertFalse(hasattr(sys, "frozen") and sys.frozen)

    def test_load_files_prompt_on_unsaved_edits(self):
        """Task 5 / U2-03: SessionManager prompts before clearing sessions when MODIFIED pages exist."""
        win = MainWindow()
        try:
            sm = win.session_manager
            sm.page_states["C:/fake/page1.png"] = PageState.MODIFIED
            self.assertTrue(sm.has_unsaved_changes())

            import cv2
            real_img_path = os.path.join(self.tmp_path, "test_page.png")
            cv2.imwrite(real_img_path, np.zeros((10, 10, 3), dtype=np.uint8))

            # User clicks "No" -> Discard cancelled
            with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No) as mock_q:
                sm.load_files([real_img_path])
                mock_q.assert_called_once()
                self.assertIn("C:/fake/page1.png", sm.page_states)
                self.assertNotIn(real_img_path, sm.page_states)

            # User clicks "Yes" -> Proceed with loading
            with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as mock_q:
                sm.load_files([real_img_path])
                mock_q.assert_called_once()
                self.assertNotIn("C:/fake/page1.png", sm.page_states)
                self.assertIn(real_img_path, sm.page_states)
        finally:
            win.timer.stop()
            win.close()

if __name__ == "__main__":
    unittest.main()
