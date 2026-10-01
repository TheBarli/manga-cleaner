import os
import cv2
import numpy as np
from collections import OrderedDict
from enum import Enum, auto
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFileDialog
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
        self.current_img_path = None
        self.max_cached_sessions = getattr(Config, "MAX_CACHED_SESSIONS", 15)

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
        valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
        files = [os.path.join(folder_path, f) for f in sorted(os.listdir(folder_path)) if f.lower().endswith(valid_exts)]
        if files:
            self.load_files(files)

    def load_files(self, file_paths: list):
        self.image_sessions.clear()
        self.page_states.clear()
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

    def _ensure_session_limit(self):
        """Evicts least recently accessed sessions when exceeding max_cached_sessions (LRU)."""
        if len(self.image_sessions) <= self.max_cached_sessions:
            return

        locked_paths = set()
        if hasattr(self.window, 'pipeline_controller'):
            locked_paths = self.window.pipeline_controller.get_locked_paths()

        while len(self.image_sessions) > self.max_cached_sessions:
            evicted = False

            # Pass 1: Prioritize evicting UNMODIFIED or READY sessions in LRU order
            for path in list(self.image_sessions.keys()):
                if path == self.current_img_path or path in locked_paths:
                    continue
                state = self.page_states.get(path, PageState.UNMODIFIED)
                if state in (PageState.UNMODIFIED, PageState.READY):
                    del self.image_sessions[path]
                    evicted = True
                    logger.debug(f"Evicted clean session from memory cache: {os.path.basename(path)}")
                    break

            # Pass 2: If still over limit, evict oldest non-locked session
            if not evicted:
                for path in list(self.image_sessions.keys()):
                    if path == self.current_img_path or path in locked_paths:
                        continue
                    del self.image_sessions[path]
                    evicted = True
                    logger.debug(f"Evicted session from memory cache: {os.path.basename(path)}")
                    break

            # If all sessions are locked or active, do not force evict
            if not evicted:
                break

    def on_file_clicked(self, it):
        path_real = it.data(Qt.UserRole)
        if path_real == self.current_img_path: return 

        if self.current_img_path and self.window.canvas.cv_img is not None:
            self.image_sessions[self.current_img_path] = {
                "img": self.window.canvas.cv_img.copy(),
                "orig": getattr(self.window.canvas, 'orig_img', self.window.canvas.cv_img).copy(),
                "mask": self.window.canvas.mask.copy(),
                "history": self.window.history
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
            img_data = np.fromfile(path_real, dtype=np.uint8)
            img = cv2.imdecode(img_data, cv2.IMREAD_UNCHANGED)

            if img is not None:
                if len(img.shape) == 2: img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                elif len(img.shape) == 3 and img.shape[2] == 4: img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                else: img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                self.window.history = HistoryManager(Config.MAX_HISTORY, on_change=self.window.update_history_ui)
                self.window.update_history_ui()
                self.window.canvas.set_image(img, orig_img=img)
                
                self.image_sessions[path_real] = {
                    "img": img.copy(),
                    "orig": img.copy(),
                    "mask": self.window.canvas.mask.copy(),
                    "history": self.window.history
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
