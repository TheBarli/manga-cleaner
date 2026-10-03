import os
import cv2
import numpy as np
from collections import OrderedDict
from enum import Enum, auto
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFileDialog, QMessageBox
from src.utils.history import HistoryManager
from src.utils.config import Config
from src.utils.paths import Paths
from src.utils.logger import logger
from src.utils.preferences import UserPrefs
from src.utils.image_io import safe_imwrite


#/////////////////////////////////#
#         PAGE STATE ENUM         #
#/////////////////////////////////#

class PageState(Enum):
    UNMODIFIED = auto()
    MODIFIED = auto()
    WAITING = auto()
    READY = auto()
    ERROR = auto()


#/////////////////////////////////#
#       SESSION MANAGER           #
#/////////////////////////////////#

class SessionManager:
    """Manages active page sessions, memory cache, file loading, switching, and exporting."""

    def __init__(self, window):
        self.window = window
        self.image_sessions = OrderedDict()
        self.page_states = {}
        self.persisted_paths = {}
        self.current_img_path = None
        self.max_cached_sessions = getattr(Config, "MAX_CACHED_SESSIONS", 15)

    def record_persisted(self, source_path: str, save_path: str):
        """Records where an image's latest processed pixels were written to disk."""
        self.persisted_paths[source_path] = save_path
        if source_path in self.image_sessions:
            self.image_sessions[source_path]["persisted_path"] = save_path

    def on_open_image(self):
        last_dir = UserPrefs.load("last_dir", "")
        p, _ = QFileDialog.getOpenFileName(self.window, "Open Image", last_dir, "Images (*.png *.jpg *.jpeg *.webp)")
        if p:
            UserPrefs.save("last_dir", os.path.dirname(p))
            self.load_single_file(p)

    def on_open_folder(self):
        last_dir = UserPrefs.load("last_dir", "")
        p = QFileDialog.getExistingDirectory(self.window, "Select Folder", last_dir)
        if p:
            UserPrefs.save("last_dir", p)
            self.load_folder(p)

    def load_single_file(self, path: str):
        if not os.path.isfile(path):
            return

        if hasattr(self.window, 'add_recent_item'):
            self.window.add_recent_item(path)

        # Synchronous check if already in file list
        found_idx = -1
        for i in range(self.window.file_list.count()):
            if self.window.file_list.item(i).data(Qt.UserRole) == path:
                found_idx = i
                break

        if found_idx >= 0:
            self.window.file_list.setCurrentRow(found_idx)
            item = self.window.file_list.item(found_idx)
            if item:
                self.on_file_clicked(item)
        else:
            self.page_states[path] = PageState.UNMODIFIED
            self.window.file_list.add_file(path)
            new_idx = self.window.file_list.count() - 1
            self.window.file_list.setCurrentRow(new_idx)
            item = self.window.file_list.item(new_idx)
            if item:
                self.on_file_clicked(item)

        self.window.canvas.fit_to_screen()

    def load_folder(self, folder_path: str):
        if not os.path.isdir(folder_path):
            return

        if hasattr(self.window, 'add_recent_item'):
            self.window.add_recent_item(folder_path)

        valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
        files = [os.path.join(folder_path, f) for f in sorted(os.listdir(folder_path)) if f.lower().endswith(valid_exts)]
        if files:
            self.load_files(files)

    def has_unsaved_changes(self) -> bool:
        """Returns True if any active or cached image has unsaved modifications."""
        return any(state == PageState.MODIFIED for state in self.page_states.values())

    def load_files(self, file_paths: list):
        if not getattr(self.window, "is_batching", False) and self.has_unsaved_changes():
            res = QMessageBox.question(
                self.window,
                "Discard Unsaved Edits?",
                "You have unsaved edits on one or more pages. Loading new files will discard them. Do you want to proceed?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if res != QMessageBox.Yes:
                return

        self.image_sessions.clear()
        self.page_states.clear()
        self.persisted_paths.clear()
        self.window.file_list.clear()
        for full_path in file_paths:
            self.page_states[full_path] = PageState.UNMODIFIED
            self.window.file_list.add_file(full_path)
        if self.window.file_list.count() > 0:
            self.window.file_list.setCurrentRow(0)
            item = self.window.file_list.item(0)
            if item:
                self.on_file_clicked(item)

    def handle_dropped_images(self, paths: list):
        if not paths:
            return
        if len(paths) == 1:
            self.load_single_file(paths[0])
        else:
            first_idx = self.window.file_list.count()
            for p in paths:
                exists = any(self.window.file_list.item(i).data(Qt.UserRole) == p for i in range(self.window.file_list.count()))
                if not exists:
                    self.page_states[p] = PageState.UNMODIFIED
                    self.window.file_list.add_file(p)
            if self.window.file_list.count() > 0:
                target_idx = first_idx if first_idx < self.window.file_list.count() else 0
                self.window.file_list.setCurrentRow(target_idx)
                item = self.window.file_list.item(target_idx)
                if item:
                    self.on_file_clicked(item)
                    self.window.canvas.fit_to_screen()

    def navigate_file(self, direction: int):
        total = self.window.file_list.count()
        if total == 0:
            return
        curr = self.window.file_list.currentRow()
        if curr < 0:
            next_idx = 0 if direction > 0 else total - 1
        else:
            next_idx = (curr + direction) % total
        self.window.file_list.setCurrentRow(next_idx)
        item = self.window.file_list.item(next_idx)
        if item:
            self.on_file_clicked(item)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
            if any(u.toLocalFile().lower().endswith(valid_exts) for u in event.mimeData().urls() if u.isLocalFile()):
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
            if any(u.toLocalFile().lower().endswith(valid_exts) for u in event.mimeData().urls() if u.isLocalFile()):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
        paths = [
            u.toLocalFile() for u in event.mimeData().urls()
            if u.isLocalFile() and u.toLocalFile().lower().endswith(valid_exts)
        ]
        if paths:
            event.acceptProposedAction()
            self.handle_dropped_images(paths)
        else:
            event.ignore()

    def mark_current_modified(self):
        """Transitions the page state to MODIFIED via Enum"""
        if self.current_img_path:
            if self.page_states.get(self.current_img_path) != PageState.MODIFIED:
                self.page_states[self.current_img_path] = PageState.MODIFIED
                self.window.file_list.update_item_state(self.current_img_path, "modified")

    def set_max_cached_sessions(self, limit: int):
        """Dynamically adjusts the maximum session limit and enforces eviction."""
        self.max_cached_sessions = max(1, limit)
        self._ensure_session_limit()

    def _is_evictable(self, path: str) -> bool:
        """A session is only safely evictable if its latest state exists intact on disk."""
        session = self.image_sessions.get(path)
        if not session:
            return False
        state = self.page_states.get(path, PageState.UNMODIFIED)
        if state == PageState.UNMODIFIED:
            return True
        persisted = session.get("persisted_path") or self.persisted_paths.get(path)
        if state == PageState.READY and persisted and os.path.exists(persisted):
            return True
        return False

    def _ensure_session_limit(self):
        """Evicts least recently accessed sessions when exceeding max_cached_sessions (LRU).
        Never evicts memory-only processed results or unsaved modifications to prevent data loss.
        """
        if len(self.image_sessions) <= self.max_cached_sessions:
            return

        locked_paths = set()
        if hasattr(self.window, 'pipeline_controller'):
            locked_paths = self.window.pipeline_controller.get_locked_paths()

        while len(self.image_sessions) > self.max_cached_sessions:
            evicted = False

            # Prioritize evicting safely persistable sessions in LRU order
            for path in list(self.image_sessions.keys()):
                if path == self.current_img_path or path in locked_paths:
                    continue
                if self._is_evictable(path):
                    del self.image_sessions[path]
                    evicted = True
                    logger.debug(f"Evicted clean/persisted session from memory cache: {os.path.basename(path)}")
                    break

            # If no sessions are evictable without data loss, stop evicting and warn
            if not evicted:
                if len(self.image_sessions) > self.max_cached_sessions:
                    if hasattr(self.window, "show_toast"):
                        self.window.show_toast("Memory cache full — export pages to free memory", "warning")
                break

    def on_file_clicked(self, it):
        path_real = it.data(Qt.UserRole)
        if path_real == self.current_img_path: return 

        if self.current_img_path and self.window.canvas.cv_img is not None:
            self.image_sessions[self.current_img_path] = {
                "img": self.window.canvas.cv_img.copy(),
                "orig": getattr(self.window.canvas, 'orig_img', self.window.canvas.cv_img).copy(),
                "mask": self.window.canvas.mask.copy(),
                "history": self.window.history,
                "persisted_path": self.persisted_paths.get(self.current_img_path)
            }
            self.image_sessions.move_to_end(self.current_img_path)
            self._ensure_session_limit()

        self.current_img_path = path_real

        if path_real in self.image_sessions:
            session = self.image_sessions[path_real]
            self.image_sessions.move_to_end(path_real)
            self.window.history = session["history"]
            self.window.history.on_change = self.window.update_history_ui
            self.window.update_history_ui()
            self.window.canvas.set_image(session["img"], orig_img=session.get("orig"))
            self.window.canvas.mask = session["mask"].copy()
            self.window.canvas.update_mask_display()
        else:
            load_source = self.persisted_paths.get(path_real, path_real)
            if not os.path.exists(load_source):
                load_source = path_real
            img_data = np.fromfile(load_source, dtype=np.uint8)
            img = cv2.imdecode(img_data, cv2.IMREAD_UNCHANGED)

            if img is not None:
                if len(img.shape) == 2: img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                elif len(img.shape) == 3 and img.shape[2] == 4: img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                else: img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                orig_img = img
                if load_source != path_real and os.path.exists(path_real):
                    orig_data = np.fromfile(path_real, dtype=np.uint8)
                    orig_dec = cv2.imdecode(orig_data, cv2.IMREAD_UNCHANGED)
                    if orig_dec is not None:
                        if len(orig_dec.shape) == 2: orig_img = cv2.cvtColor(orig_dec, cv2.COLOR_GRAY2RGB)
                        elif len(orig_dec.shape) == 3 and orig_dec.shape[2] == 4: orig_img = cv2.cvtColor(orig_dec, cv2.COLOR_BGRA2RGBA)
                        else: orig_img = cv2.cvtColor(orig_dec, cv2.COLOR_BGR2RGB)

                self.window.history = HistoryManager(Config.MAX_HISTORY, on_change=self.window.update_history_ui)
                self.window.update_history_ui()
                self.window.canvas.set_image(img, orig_img=orig_img)
                
                self.image_sessions[path_real] = {
                    "img": img.copy(),
                    "orig": orig_img.copy(),
                    "mask": self.window.canvas.mask.copy(),
                    "history": self.window.history,
                    "persisted_path": self.persisted_paths.get(path_real)
                }
                self.image_sessions.move_to_end(path_real)
                self._ensure_session_limit()
            else:
                self.window.show_toast(f"Corrupted or invalid image: {os.path.basename(path_real)}", "error")
                logger.error(f"Failed to decode image: {path_real}")
                
        # Update status bar file name, dimensions & color mode
        if hasattr(self.window, 'status_file_lbl'):
            self.window.status_file_lbl.setText(os.path.basename(path_real))
            self.window.status_file_lbl.setToolTip(path_real)

        if hasattr(self.window, 'status_dim_lbl') and self.window.canvas.cv_img is not None:
            h, w = self.window.canvas.cv_img.shape[:2]
            channels = "RGBA" if (len(self.window.canvas.cv_img.shape) == 3 and self.window.canvas.cv_img.shape[2] == 4) else "RGB"
            self.window.status_dim_lbl.setText(f"{w} × {h} px · {channels}")

        self.window._check_lock_state()
        self.window.canvas.setFocus()

    def on_quick_save(self):
        if self.window.canvas.cv_img is None or not self.current_img_path:
            self.window.show_toast("No active image to save", "warning")
            return

        os.makedirs(Paths.PROCESSED, exist_ok=True)
        filename = os.path.basename(self.current_img_path)
        out_path = os.path.join(Paths.PROCESSED, filename)

        img = self.window.canvas.cv_img
        if len(img.shape) == 3 and img.shape[2] == 4:
            img_out = cv2.cvtColor(img, cv2.COLOR_RGBA2BGRA)
            ext = os.path.splitext(out_path)[1].lower()
            if ext in [".jpg", ".jpeg"]:
                img_out = cv2.cvtColor(img_out, cv2.COLOR_BGRA2BGR)
        else:
            img_out = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        ext = os.path.splitext(out_path)[1]
        if not ext:
            out_path += ".png"
            ext = ".png"

        success, buf = cv2.imencode(ext, img_out)
        if success:
            buf.tofile(out_path)
            self.record_persisted(self.current_img_path, out_path)
            self.page_states[self.current_img_path] = PageState.READY
            self.window.file_list.update_item_state(self.current_img_path, "ready")
            self.window.show_toast(f"Quick-saved: {filename}", "success")
        else:
            self.window.show_toast("Failed to encode image", "error")

    def on_export(self, fmt=None):
        if self.window.canvas.cv_img is None: return
        last_export_dir = UserPrefs.load("last_export_dir", UserPrefs.load("last_dir", ""))
        default_dir = os.path.join(last_export_dir, "") if last_export_dir else ""
        path, sel_filter = QFileDialog.getSaveFileName(
            self.window, "Export Image", default_dir, "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)"
        )
        if path:
            UserPrefs.save("last_export_dir", os.path.dirname(path))
            ext = os.path.splitext(path)[1].lower().lstrip(".")
            if not ext:
                ext = "png" if "PNG" in sel_filter else "jpg"
                path = f"{path}.{ext}"
            chosen_fmt = ext
            if len(self.window.canvas.cv_img.shape) == 3 and self.window.canvas.cv_img.shape[2] == 4:
                img_out = cv2.cvtColor(self.window.canvas.cv_img, cv2.COLOR_RGBA2BGRA)
                if chosen_fmt in ["jpg", "jpeg"]:
                    img_out = cv2.cvtColor(img_out, cv2.COLOR_BGRA2BGR)
            else:
                img_out = cv2.cvtColor(self.window.canvas.cv_img, cv2.COLOR_RGB2BGR)
                
            if safe_imwrite(path, img_out):
                self.window.show_toast(f"Exported: {os.path.basename(path)}", "success")
            else:
                self.window.show_toast("Failed to export image", "error")

    def on_send_to_photopea(self):
        """Transfers original and cleaned image to Photopea in browser as separate layers."""
        if self.window.canvas.cv_img is None:
            self.window.show_toast("No active image to send", "warning")
            return

        cleaned_rgb = self.window.canvas.cv_img
        original_rgb = self.window.canvas.orig_img if self.window.canvas.orig_img is not None else cleaned_rgb
        img_path = self.current_img_path

        try:
            from src.backend.bridges.photopea import PhotopeaBridge
            res = PhotopeaBridge.send_to_photopea(original_rgb, cleaned_rgb, img_path)
            if res == "Success":
                self.window.show_toast("Opening in Photopea...", "success")
            else:
                self.window.show_toast(f"Photopea bridge error: {res}", "error")
        except Exception as e:
            logger.error(f"Failed to send to Photopea: {e}", exc_info=True)
            self.window.show_toast(f"Photopea error: {e}", "error")

    def on_send_to_photoshop(self):
        """Transfers original and cleaned image to Adobe Photoshop via COM."""
        if self.window.canvas.cv_img is None:
            self.window.show_toast("No active image to send", "warning")
            return

        cleaned_rgb = self.window.canvas.cv_img
        original_rgb = self.window.canvas.orig_img if self.window.canvas.orig_img is not None else cleaned_rgb

        try:
            from src.backend.bridges.photoshop import PhotoshopBridge
            res = PhotoshopBridge.send_to_ps(original_rgb, cleaned_rgb)
            if res == "Success":
                self.window.show_toast("Transferred to Photoshop", "success")
            else:
                self.window.show_toast(f"Photoshop bridge error: {res}", "error")
        except Exception as e:
            logger.error(f"Failed to send to Photoshop: {e}", exc_info=True)
            self.window.show_toast(f"Photoshop error: {e}", "error")
