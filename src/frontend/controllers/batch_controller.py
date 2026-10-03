import os
import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog
from src.backend.batch_engine import BatchEngine
from src.frontend.dialogs.batch_setup import BatchSetupDialog
from src.frontend.controllers.session_manager import PageState
from src.utils.history import HistoryManager
from src.utils.config import Config


#/////////////////////////////////#
#       BATCH CONTROLLER          #
#/////////////////////////////////#

class BatchController:
    """Coordinates batch processing workflow, configuration dialogs, and step execution."""

    def __init__(self, window):
        self.window = window
        self.batch_engine = BatchEngine()
        self.is_batching = False
        self.batch_scan_type = "ocr"

    def _reset_batch_button(self):
        """Restores batch action button to default state."""
        self.window.btn_batch.setText("RUN BATCH PROCESS")
        self.window.btn_batch.setStyleSheet("")
        self.window.btn_batch.setToolTip("Run Batch Clean")

    def _set_batching_button(self):
        """Sets batch action button to active cancellation state."""
        self.window.btn_batch.setText("CANCEL BATCH")
        self.window.btn_batch.setStyleSheet("background-color: #dc2626; color: #ffffff; font-weight: bold;")
        self.window.btn_batch.setToolTip("Cancel running batch process")

    def on_start_batch(self):
        """Opens batch setup dialog and initializes batch processing for selected or all files."""
        if self.is_batching:
            self.cancel_batch()
            return

        if self.window.file_list.count() == 0:
            return

        total_count = self.window.file_list.count()
        selected_count = sum(1 for i in range(total_count) if self.window.file_list.item(i).checkState() == Qt.Checked)
        dialog = BatchSetupDialog(self.window, selected_count=selected_count, total_count=total_count)
        if dialog.exec() != QDialog.Accepted:
            return

        scan_choice, fmt = dialog.get_results()
        if scan_choice == "Transparency Scan":
            self.batch_scan_type = "transparency"
        elif scan_choice == "Mask":
            self.batch_scan_type = "mask"
        elif scan_choice == "none":
            self.batch_scan_type = "none"
        else:
            self.batch_scan_type = "ocr"

        # Check if any specific files were checked in the UI
        paths = []
        for i in range(self.window.file_list.count()):
            item = self.window.file_list.item(i)
            if item.checkState() == Qt.Checked:
                paths.append(item.data(Qt.UserRole))

        # If absolutely no checkboxes are checked, default to ALL files
        if not paths:
            self.window.chk_all.setChecked(True)
            paths = [self.window.file_list.item(i).data(Qt.UserRole) for i in range(self.window.file_list.count())]

        self.batch_engine.initialize_batch(paths, fmt)
        self.is_batching = True
        self._set_batching_button()
        self.window.pipeline_controller.total_lama_tasks += len(paths)
        self.step_batch()
        self.window.pipeline_controller._check_lock_state()

    def step_batch(self):
        """Pulls the next file in batch sequence and triggers the required scan/clean/save action."""
        if not self.is_batching:
            return

        path = self.batch_engine.get_next()
        if path:
            if path not in self.window.image_sessions:
                img_data = np.fromfile(path, dtype=np.uint8)
                img = cv2.imdecode(img_data, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    if len(img.shape) == 2:
                        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                    elif len(img.shape) == 3 and img.shape[2] == 4:
                        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                    else:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                    self.window.image_sessions[path] = {
                        "img": img.copy(),
                        "orig": img.copy(),
                        "mask": QImage(img.shape[1], img.shape[0], QImage.Format_ARGB32),
                        "history": HistoryManager(Config.MAX_HISTORY)
                    }
                    self.window.image_sessions[path]["mask"].fill(Qt.transparent)
                    if hasattr(self.window.session_manager.image_sessions, 'move_to_end'):
                        self.window.session_manager.image_sessions.move_to_end(path)
                    self.window.session_manager._ensure_session_limit()
            else:
                if hasattr(self.window.session_manager.image_sessions, 'move_to_end'):
                    self.window.session_manager.image_sessions.move_to_end(path)

            is_active = (path == self.window.current_img_path)

            if self.batch_scan_type == "none":
                img_cv = self.window.canvas.cv_img if is_active else self.window.image_sessions[path]["img"]
                self.window.pipeline_controller.total_lama_tasks -= 1
                
                self.window.page_states[path] = PageState.READY
                self.window.file_list.update_item_state(path, "ready")
                self.window.pipeline_controller._update_queue_ui()
                
                is_last = self.batch_engine.save_current(img_cv)
                if is_last:
                    self.finalize_batch()
                else:
                    QTimer.singleShot(0, self.step_batch)
                return
                
            elif self.batch_scan_type == "mask":
                mask_q = self.window.canvas.mask if is_active else self.window.image_sessions[path]["mask"]
                img_cv = self.window.canvas.cv_img if is_active else self.window.image_sessions[path]["img"]

                ptr = mask_q.bits()
                mask_np = np.frombuffer(ptr, np.uint8).reshape((mask_q.height(), mask_q.width(), 4))
                mask_gray = mask_np[:, :, 3].copy()

                if not np.any(mask_gray):
                    self.window.pipeline_controller.total_lama_tasks -= 1
                    self.window.page_states[path] = PageState.READY
                    self.window.file_list.update_item_state(path, "ready")
                    self.window.pipeline_controller._update_queue_ui()
                    
                    is_last = self.batch_engine.save_current(img_cv)
                    if is_last:
                        self.finalize_batch()
                    else:
                        QTimer.singleShot(0, self.step_batch)
                    return

                t_size = self.window.t_slider.slider.value() * 512
                self.window.pipeline_controller.enqueue_task("clean", path, img_cv.copy(), mask_gray, t_size)
            else:
                img_cv = self.window.canvas.cv_img if is_active else self.window.image_sessions[path]["img"]
                self.window.pipeline_controller.enqueue_task(self.batch_scan_type, path, img_cv.copy())

    def handle_task_finished(self, task: str, source_path: str, is_active: bool):
        """Advances batch processing upon AI task completion."""
        if not self.is_batching:
            return

        if task == "clean":
            final_img = self.window.canvas.cv_img if is_active else self.window.image_sessions[source_path]["img"]
            if self.batch_engine.export_format.lower() != "none":
                ext = self.batch_engine.export_format.lower()
                orig_name = os.path.splitext(os.path.basename(source_path))[0]
                save_path = os.path.join(self.batch_engine.output_dir, f"{orig_name}_cleaned.{ext}")
                self.window.session_manager.record_persisted(source_path, save_path)
            is_last = self.batch_engine.save_current(final_img)
            self.window.session_manager._ensure_session_limit()
            if is_last:
                self.finalize_batch()
            else:
                self.step_batch()
        elif task in ["ocr", "transparency"]:
            mask_q = self.window.canvas.mask if is_active else self.window.image_sessions[source_path]["mask"]
            img_cv = self.window.canvas.cv_img if is_active else self.window.image_sessions[source_path]["img"]

            ptr = mask_q.bits()
            mask_np = np.frombuffer(ptr, np.uint8).reshape((mask_q.height(), mask_q.width(), 4))
            mask_gray = mask_np[:, :, 3].copy()
            t_size = self.window.t_slider.slider.value() * 512
            self.window.pipeline_controller.enqueue_task("clean", source_path, img_cv.copy(), mask_gray, t_size)

    def cancel_batch(self):
        """Cancels running batch process, purges pending queue, and restores UI state."""
        if not self.is_batching:
            return

        self.is_batching = False
        self.batch_engine.files.clear()
        self.batch_engine.current_index = 0

        # Purge pending pipeline tasks
        self.window.pipeline_controller.task_queue.clear()
        self.window.pipeline_controller.total_lama_tasks = 0
        self.window.pipeline_controller.completed_lama_tasks = 0
        self.window.pipeline_controller.total_tasks = 0
        self.window.pipeline_controller.completed_tasks = 0

        self._reset_batch_button()
        self.window.pipeline_controller._update_queue_ui()
        self.window.pipeline_controller._check_lock_state()
        self.window.show_toast("Batch process cancelled", "warning")

    def finalize_batch(self):
        """Completes the batch cycle and alerts the user."""
        self.is_batching = False
        self._reset_batch_button()
        self.window.pipeline_controller._check_lock_state()
            
        if self.batch_engine.export_format == "none":
            self.window.show_toast("Batch Complete: Pages updated in studio memory", "success", 4000)
        else:
            self.window.show_toast(f"Batch Complete: Saved to {os.path.basename(self.batch_engine.output_dir)}", "success", 4000)
