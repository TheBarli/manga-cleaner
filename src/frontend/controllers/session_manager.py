import os
import cv2
import numpy as np
from enum import Enum, auto
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFileDialog
from src.utils.history import HistoryManager
from src.utils.config import Config
from src.utils.paths import Paths
from src.utils.logger import logger


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
        self.image_sessions = {}
        self.page_states = {}
        self.current_img_path = None

    def on_open_image(self):
        p, _ = QFileDialog.getOpenFileName(self.window, "Open Image", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if p:
            self.load_single_file(p)

    def on_open_folder(self):
        p = QFileDialog.getExistingDirectory(self.window, "Select Folder")
        if p:
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

        self.current_img_path = path_real

        if path_real in self.image_sessions:
            session = self.image_sessions[path_real]
            self.window.history = session["history"]
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

                self.window.history = HistoryManager(Config.MAX_HISTORY)
                self.window.canvas.set_image(img, orig_img=img)
                
                self.image_sessions[path_real] = {
                    "img": img.copy(),
                    "orig": img.copy(),
                    "mask": self.window.canvas.mask.copy(),
                    "history": self.window.history
                }
            else:
                self.window.show_toast(f"Corrupted or invalid image: {os.path.basename(path_real)}", "error")
                logger.error(f"Failed to decode image: {path_real}")
                
        # Update status bar dimensions & color mode
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
        path, sel_filter = QFileDialog.getSaveFileName(
            self.window, "Export Image", "", "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)"
        )
        if path:
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
                
            is_success, im_buf_arr = cv2.imencode(f".{chosen_fmt}", img_out)
            if is_success:
                im_buf_arr.tofile(path)
                self.window.show_toast(f"Exported: {os.path.basename(path)}", "success")
