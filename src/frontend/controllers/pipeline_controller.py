import numpy as np
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox
from src.backend.workers import AIWorker
from src.frontend.controllers.session_manager import PageState
from src.utils.logger import logger


#/////////////////////////////////#
#      PIPELINE CONTROLLER        #
#/////////////////////////////////#

class PipelineController:
    """Manages AI task queuing, worker thread lifecycles, inference scheduling, and history undo/redo."""

    def __init__(self, window):
        self.window = window
        self.worker_thread = None
        self.worker = None
        self.task_queue = []
        self.total_tasks = 0
        self.completed_tasks = 0
        self.total_lama_tasks = 0
        self.completed_lama_tasks = 0
        self._ocr_initialized = False
        self._lama_initialized = False

    def get_locked_paths(self) -> set:
        """Returns set of all file paths currently running or queued in AI pipeline or batch."""
        locked_paths = set()
        
        # 1. Grab file currently running in AI worker thread
        if self.worker_thread is not None and hasattr(self, 'worker') and self.worker:
            active_path = getattr(self.worker, 'source_path', None)
            if active_path:
                locked_paths.add(active_path)
            
        # 2. Grab all manual/single-task queued files
        for item in self.task_queue:
            locked_paths.add(item["path"])
                
        # 3. Grab all remaining files waiting in the Batch Engine queue
        if self.window.is_batching:
            batch_eng = self.window.batch_engine
            for idx in range(batch_eng.current_index, len(batch_eng.files)):
                locked_paths.add(batch_eng.files[idx])

        return locked_paths

    def _check_lock_state(self):
        """Identifies ALL files currently being processed or waiting and globally updates UI."""
        locked_paths = self.get_locked_paths()

        # 4. Globally update the FileList UI checkboxes and lock icons
        for i in range(self.window.file_list.count()):
            item = self.window.file_list.item(i)
            file_path = item.data(Qt.UserRole)
            is_locked = (file_path in locked_paths)
            item.setData(Qt.UserRole + 2, is_locked)

        # 5. Lock/Unlock the main interactive Canvas if we're looking at a locked file
        if self.window.current_img_path:
            self.window.canvas.set_locked(self.window.current_img_path in locked_paths)
        else:
            self.window.canvas.set_locked(False)

    def _update_queue_ui(self):
        """Updates the status label, global progress bar, and active lock states."""
        pending = max(0, self.total_lama_tasks - self.completed_lama_tasks)
        self.window.queue_lbl.setText(f"Processing / Queued: {pending}")

        if pending > 0 and self.total_lama_tasks > 0:
            val = int((self.completed_lama_tasks / self.total_lama_tasks) * 100)
            self.window.progress_bar.setValue(val)
            self.window.progress_bar.setVisible(True)
        else:
            self.window.progress_bar.setVisible(False)
            self.total_lama_tasks = 0
            self.completed_lama_tasks = 0
            
        self._check_lock_state()

    def on_worker_progress(self, val):
        """Calculates fractional progress for smooth overall queue tracking."""
        if hasattr(self.window, 'progress_bar') and self.window.progress_bar.maximum() == 0:
            self.window.progress_bar.setRange(0, 100)
        if self.worker.task != "clean" or self.total_lama_tasks == 0:
            return
        base_progress = (self.completed_lama_tasks / self.total_lama_tasks) * 100
        task_fraction = (val / 100.0) * (100 / self.total_lama_tasks)
        self.window.progress_bar.setValue(int(base_progress + task_fraction))

    def enqueue_task(self, task: str, path: str, *args):
        """Pushes an AI task into the FIFO queue and triggers the processor."""
        self.task_queue.append({
            "task": task,
            "path": path,
            "args": args
        })
        self._update_queue_ui()
        self._process_queue()

    def _process_queue(self):
        """Pulls the next task from the queue and runs it."""
        if self.worker_thread is not None:
            return

        if not self.task_queue:
            self._update_queue_ui()
            # Models stay resident in VRAM for instant subsequent inferences
            return

        item = self.task_queue.pop(0)
        source_path = item["path"]
        task = item["task"]

        # First-time model loading progress feedback
        if task == "ocr" and not self._ocr_initialized:
            self._ocr_initialized = True
            self.window.show_toast("Loading OCR detection model into VRAM...", "info", 5000)
            self.window.canvas.show_hud("Loading OCR Model...", duration=3500)
            self.window.progress_bar.setRange(0, 0)
            self.window.progress_bar.setVisible(True)
        elif task == "clean" and not self._lama_initialized:
            self._lama_initialized = True
            self.window.show_toast("Loading LaMa inpainting model into VRAM...", "info", 5000)
            self.window.canvas.show_hud("Loading LaMa Model...", duration=3500)
            if not self.window.is_batching:
                self.window.progress_bar.setRange(0, 0)
                self.window.progress_bar.setVisible(True)
        
        # Update status to WAITING since AI is processing it now
        self.window.page_states[source_path] = PageState.WAITING
        self.window.file_list.update_item_state(source_path, "waiting")

        self.window.setCursor(Qt.WaitCursor)
        self.worker_thread = QThread()
        self.worker = AIWorker(item["task"], item["args"])
        self.worker.source_path = source_path

        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.process)
        self.worker.progress.connect(self.on_worker_progress)
        self.worker.finished.connect(self.on_task_finished)
        self.worker.error.connect(self.on_task_error)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        self.worker_thread.start()
        self._update_queue_ui() 

    def stop_thread(self):
        """Terminates active worker thread and restores cursor."""
        self.window.setCursor(Qt.ArrowCursor)
        if hasattr(self.window, 'progress_bar') and self.window.progress_bar.maximum() == 0:
            self.window.progress_bar.setRange(0, 100)
        if hasattr(self, 'worker') and self.worker:
            self.worker.cancel()
        if self.worker_thread:
            self.worker_thread.quit()
            if not self.worker_thread.wait(3000):
                logger.warning("[!] Worker thread did not terminate within 3s, terminating...")
                self.worker_thread.terminate()
                self.worker_thread.wait(1000)
            self.worker_thread = None
        self._update_queue_ui()

    def on_task_error(self, message: str):
        """Handles worker failure, marks error state, and displays crash alert."""
        try:
            source_path = getattr(self.worker, 'source_path', None)
            if source_path:
                self.window.page_states[source_path] = PageState.ERROR
                self.window.file_list.update_item_state(source_path, "error")

            self.window.batch_controller.is_batching = False
            self.task_queue.clear()
            self.total_lama_tasks = 0
            self.completed_lama_tasks = 0
            QMessageBox.critical(self.window, "Hardware Error", message)
        finally:
            self.stop_thread()
            self._update_queue_ui()

    def on_task_finished(self, result, patches):
        """Applies inference results to active canvas or background session."""
        try:
            task = self.worker.task if self.worker else "unknown"
            source_path = getattr(self.worker, 'source_path', self.window.current_img_path)
            is_active = (source_path == self.window.current_img_path)

            session = self.window.image_sessions.get(source_path)
            if not is_active and session is None:
                logger.warning(f"[!] Session for {source_path} no longer exists; discarding finished {task} task.")
                return

            new_state = PageState.READY if task == "clean" else PageState.MODIFIED
            self.window.page_states[source_path] = new_state
            self.window.file_list.update_item_state(source_path, new_state.name.lower())

            if hasattr(self.window, 'progress_bar') and self.window.progress_bar.maximum() == 0:
                self.window.progress_bar.setRange(0, 100)

            if task == "clean":
                if self.completed_lama_tasks < self.total_lama_tasks:
                    self.completed_lama_tasks += 1
                target_history = self.window.history if is_active else session["history"]
                saved_mask = self.window.canvas.mask.copy() if is_active else session["mask"].copy()
                if len(patches) > 0:
                    target_history.push_image_clean(patches, result, saved_mask=saved_mask)

                if is_active:
                    self.window.canvas.set_image(result)
                else:
                    session["img"] = result
                    session["mask"].fill(Qt.transparent)

            elif task in ["ocr", "transparency"]:
                target_history = self.window.history if is_active else session["history"]
                current_mask = self.window.canvas.mask if is_active else session["mask"]
                target_history.push_mask_state(current_mask)

                h, w = result.shape[:2]
                rgba = np.zeros((h, w, 4), dtype=np.uint8)
                if task == "transparency":
                    color_bgra = [0, 255, 0, 255]
                else:
                    c = getattr(self.window.canvas, 'current_mask_color', None)
                    if c is not None:
                        color_bgra = [c.blue(), c.green(), c.red(), 255]
                    else:
                        color_bgra = [94, 63, 244, 255]
                rgba[result > 0] = color_bgra
                new_mask = QImage(rgba.data, w, h, w * 4, QImage.Format_ARGB32).copy()

                if is_active:
                    self.window.canvas.mask = new_mask
                    self.window.canvas.update_mask_display()
                else:
                    session["mask"] = new_mask

            # Handle Background Batching Loop
            if self.window.is_batching:
                self.window.batch_controller.handle_task_finished(task, source_path, is_active)
        except Exception as e:
            logger.error(f"[X] Unexpected error applying task result for {source_path}: {e}", exc_info=True)
        finally:
            self.stop_thread()
            self._process_queue()

    def on_ocr_scan(self):
        """Triggers text detection inference on the active canvas."""
        if self.window.canvas.cv_img is None or self.window.canvas.is_locked:
            return
        self.window.mark_current_modified()
        self.enqueue_task("ocr", self.window.current_img_path, self.window.canvas.cv_img.copy())

    def on_transparency_scan(self):
        """Triggers alpha/transparency detection on the active canvas."""
        if self.window.canvas.cv_img is None or not self.window.current_img_path or self.window.canvas.is_locked:
            return
        self.window.mark_current_modified()
        self.enqueue_task("transparency", self.window.current_img_path, self.window.canvas.cv_img.copy())

    def on_lama_clean(self):
        """Validates mask area and triggers LaMa inpainting inference."""
        if self.window.canvas.cv_img is None or self.window.canvas.is_locked:
            return
        ptr = self.window.canvas.mask.bits()
        mask_np = np.frombuffer(ptr, np.uint8).reshape((self.window.canvas.mask.height(), self.window.canvas.mask.width(), 4))
        mask_gray = mask_np[:, :, 3].copy()

        if not np.any(mask_gray):
            if self.window.is_batching:
                is_last = self.window.batch_engine.save_current(self.window.canvas.cv_img)
                if is_last:
                    self.window.batch_controller.finalize_batch()
                else:
                    self.window.batch_controller.step_batch()
            else:
                self.window.show_toast("No mask area detected", "warning")
            return

        if not self.window.is_batching:
            mask_coverage = np.count_nonzero(mask_gray) / mask_gray.size
            if mask_coverage > 0.30:
                reply = QMessageBox.question(
                    self.window,
                    "Large Mask Warning",
                    f"The active mask covers {int(mask_coverage * 100)}% of the image.\n"
                    "Inpainting such a large area may take substantial processing time.\n\n"
                    "Do you want to proceed with AI cleaning?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return

        self.total_lama_tasks += 1
        t_size = self.window.t_slider.slider.value() * 512
        self.window.mark_current_modified()
        self.enqueue_task("clean", self.window.current_img_path, self.window.canvas.cv_img.copy(), mask_gray, t_size)

    #/////////////////////////////////#
    #      HISTORY OPERATIONS         #
    #/////////////////////////////////#

    def on_undo(self):
        """Reverts the last mask edit or inpainting patch."""
        if self.window.canvas.is_locked:
            return
        res = self.window.history.undo(self.window.canvas.cv_img, self.window.canvas.mask)
        if not res:
            return

        self.window.mark_current_modified()
        if res.get("type") == "mask":
            self.window.canvas.mask = res["mask"].copy()
            self.window.canvas.update_mask_display()
        elif res.get("type") == "image":
            self.window.canvas.set_image(res["img"])
            if res.get("restore_mask") is not None:
                self.window.canvas.mask = res["restore_mask"].copy()
                self.window.canvas.update_mask_display()

    def on_redo(self):
        """Re-applies the next mask edit or inpainting patch."""
        if self.window.canvas.is_locked:
            return
        res = self.window.history.redo(self.window.canvas.cv_img, self.window.canvas.mask)
        if not res:
            return

        self.window.mark_current_modified()
        if res.get("type") == "mask":
            self.window.canvas.mask = res["mask"].copy()
            self.window.canvas.update_mask_display()
        elif res.get("type") == "image":
            self.window.canvas.set_image(res["img"])
            if res.get("clear_mask"):
                self.window.canvas.reset_mask()

    def on_undo_image(self):
        self.on_undo()

    def on_redo_image(self):
        self.on_redo()

    def on_undo_mask(self):
        self.on_undo()

    def on_redo_mask(self):
        self.on_redo()
