import os
import cv2
from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, 
                             QGraphicsPathItem, QGraphicsEllipseItem, QLabel,
                             QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QMenu)
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush, QPainterPath, QIcon, QCursor, QKeySequence
from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QTimer
import numpy as np
from src.utils.paths import Paths
from src.utils.config import Config
from src.utils.preferences import UserPrefs


#/////////////////////////////////#
#       WELCOME EMPTY STATE       #
#/////////////////////////////////#

class WelcomeOverlay(QFrame):
    """Centered empty-state overlay displayed on the canvas when no image is loaded."""
    open_image_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WelcomeOverlay")
        self.setAcceptDrops(True)
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 28, 36, 28)
        lay.setSpacing(12)
        lay.setAlignment(Qt.AlignCenter)

        # Title
        title = QLabel("MANGA CLEANER STUDIO")
        title.setObjectName("WelcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {Config.COLOR_TEXT_PRIMARY}; font-size: 17px; font-weight: bold; letter-spacing: 1px;")

        # Subtitle
        subtitle = QLabel("AI Inpainting & Speech Bubble Cleaner")
        subtitle.setObjectName("WelcomeSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-size: 11px; font-weight: bold; text-transform: uppercase;")

        # Instructions
        desc = QLabel("Drag & drop manga pages here\nor choose an option below to get started")
        desc.setObjectName("WelcomeDesc")
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(f"color: {Config.COLOR_TEXT_MUTED}; font-size: 12px; line-height: 1.4;")

        # Action Buttons
        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(12)
        btn_lay.setAlignment(Qt.AlignCenter)

        self.btn_open_img = QPushButton("Open Image")
        self.btn_open_img.setCursor(Qt.PointingHandCursor)
        self.btn_open_img.setStyleSheet(f"""
            QPushButton {{
                background-color: {Config.COLOR_ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Config.COLOR_ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {Config.COLOR_ACCENT_ACTIVE};
            }}
        """)
        self.btn_open_img.clicked.connect(self.open_image_requested.emit)

        self.btn_open_folder = QPushButton("Import Folder")
        self.btn_open_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_folder.setStyleSheet(f"""
            QPushButton {{
                background-color: {Config.COLOR_BG_SURFACE};
                color: {Config.COLOR_TEXT_PRIMARY};
                border: 1px solid {Config.COLOR_BORDER_SUBTLE};
                border-radius: 6px;
                padding: 8px 18px;
                font-weight: 500;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Config.COLOR_BG_HOVER};
                border-color: {Config.COLOR_ACCENT};
            }}
        """)
        self.btn_open_folder.clicked.connect(self.open_folder_requested.emit)

        btn_lay.addWidget(self.btn_open_img)
        btn_lay.addWidget(self.btn_open_folder)

        # Shortcuts hint
        hints = QLabel("Ctrl+O: Open Image   ·   Ctrl+Shift+O: Open Folder   ·   F1: Help")
        hints.setAlignment(Qt.AlignCenter)
        hints.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px; margin-top: 4px;")

        lay.addWidget(title)
        lay.addWidget(subtitle)
        lay.addSpacing(4)
        lay.addWidget(desc)
        lay.addSpacing(6)
        lay.addLayout(btn_lay)
        lay.addWidget(hints)

        self.setStyleSheet(f"""
            QFrame#WelcomeOverlay {{
                background-color: rgba(30, 30, 30, 235);
                border: 1px solid {Config.COLOR_BORDER_SUBTLE};
                border-radius: 12px;
            }}
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
        paths = [
            u.toLocalFile() for u in event.mimeData().urls()
            if u.isLocalFile() and u.toLocalFile().lower().endswith(valid_exts)
        ]
        if paths and self.parent():
            event.acceptProposedAction()
            self.parent().images_dropped.emit(paths)
        else:
            event.ignore()


#/////////////////////////////////#
#       NAVIGATOR MINIMAP         #
#/////////////////////////////////#

class MinimapWidget(QFrame):
    """
    Interactive floating minimap/navigator overlay for MangaCanvas.
    Shows full image thumbnail with a highlighted viewport rectangle indicating
    the current visible region. Clicking/dragging navigates the canvas viewport.
    """
    pan_requested = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MinimapWidget")
        self.setFixedSize(140, 180)
        self.setStyleSheet("""
            QFrame#MinimapWidget {
                background-color: rgba(26, 26, 30, 220);
                border: 1px solid #4a4a52;
                border-radius: 6px;
            }
        """)
        self.thumbnail_pixmap = None
        self.viewport_rect = QRectF()
        self.is_dragging = False
        self.hide()

    def set_image(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            avail_w = self.width() - 16
            avail_h = self.height() - 16
            self.thumbnail_pixmap = pixmap.scaled(avail_w, avail_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            self.thumbnail_pixmap = None
        self.update()

    def set_viewport_rect(self, norm_rect: QRectF):
        self.viewport_rect = norm_rect
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.thumbnail_pixmap:
            return

        tx = (self.width() - self.thumbnail_pixmap.width()) // 2
        ty = (self.height() - self.thumbnail_pixmap.height()) // 2
        painter.drawPixmap(tx, ty, self.thumbnail_pixmap)

        tw = self.thumbnail_pixmap.width()
        th = self.thumbnail_pixmap.height()

        vx = tx + self.viewport_rect.x() * tw
        vy = ty + self.viewport_rect.y() * th
        vw = max(4.0, min(float(tw), self.viewport_rect.width() * tw))
        vh = max(4.0, min(float(th), self.viewport_rect.height() * th))

        vp_rect = QRectF(vx, vy, vw, vh)

        painter.setBrush(QBrush(QColor(200, 110, 0, 45)))
        painter.setPen(QPen(QColor(200, 110, 0, 220), 1.5))
        painter.drawRect(vp_rect)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.thumbnail_pixmap:
            self.is_dragging = True
            self._handle_mouse_nav(event.pos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging and self.thumbnail_pixmap:
            self._handle_mouse_nav(event.pos())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_dragging:
            self.is_dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _handle_mouse_nav(self, pos):
        if not self.thumbnail_pixmap:
            return
        tx = (self.width() - self.thumbnail_pixmap.width()) // 2
        ty = (self.height() - self.thumbnail_pixmap.height()) // 2
        tw = self.thumbnail_pixmap.width()
        th = self.thumbnail_pixmap.height()

        rel_x = max(0.0, min(1.0, (pos.x() - tx) / max(1, tw)))
        rel_y = max(0.0, min(1.0, (pos.y() - ty) / max(1, th)))
        self.pan_requested.emit(rel_x, rel_y)


#/////////////////////////////////#
#   MULTI-TOOL CANVAS ENGINE      #
#/////////////////////////////////#

class MangaCanvas(QGraphicsView):
    mask_changed = Signal()
    brush_size_changed = Signal(int)
    mouse_moved = Signal(int, int)
    zoom_changed = Signal(int)
    images_dropped = Signal(list)
    open_image_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        # --- GENERATE CHECKERBOARD BACKGROUND ---
        grid_size = 10
        checkerboard = QPixmap(grid_size * 2, grid_size * 2)
        checkerboard.fill(QColor(255, 255, 255))
        painter = QPainter(checkerboard)
        painter.fillRect(0, 0, grid_size, grid_size, QColor(200, 200, 200))
        painter.fillRect(grid_size, grid_size, grid_size, grid_size, QColor(200, 200, 200))
        painter.end()
        self.setBackgroundBrush(QBrush(checkerboard))

        self.image_item = QGraphicsPixmapItem()
        self.mask_item = QGraphicsPixmapItem()
        self.mask_item.setOpacity(60 / 100.0)
        self.scene.addItem(self.image_item)
        self.scene.addItem(self.mask_item)

        self.cursor_item = QGraphicsEllipseItem()
        self.cursor_item.setZValue(1000)
        self.cursor_item.hide() # Start hidden!
        self.scene.addItem(self.cursor_item)

        self.current_tool = "NONE"
        self.brush_size = 40
        self.is_drawing = False
        self.is_locked = False  
        self.is_resizing_brush = False
        self.resize_start_pos = None
        self.resize_start_size = 40
        self.resize_start_cursor_pos = None
        
        # Navigation & Viewport State
        self.is_middle_panning = False
        self.middle_pan_start = None
        self.is_flipped_h = False
        self.orig_img = None
        self.is_comparing = False
        self.is_mask_hidden = False

        # Multi-Color Mask System
        self.mask_colors = [
            QColor(200, 110, 0, 255),  # Studio Amber
            QColor(6, 182, 212, 255),  # Teal Cyan
            QColor(132, 204, 22, 255), # Lime Green
            QColor(244, 63, 94, 255)   # Coral Red
        ]
        self.mask_color_names = ["Studio Amber", "Teal Cyan", "Lime Green", "Coral Red"]
        self.mask_color_idx = 0
        self.current_mask_color = self.mask_colors[0]

        self.last_pt = QPointF()
        self.start_pt = QPointF()
        self.last_drawn_pt = None # Remembers position for Shift+Click straight lines
        self.lasso_path = QPainterPath()
        self.poly_points = []
        self.preview_item = QGraphicsPathItem()
        self.preview_item.setPen(QPen(QColor(200, 110, 0, 200), 2, Qt.DashLine)) # Studio amber
        self.scene.addItem(self.preview_item)

        # --- BIG CORNER LOCK OVERLAY ---
        self.lock_overlay = QLabel(self)
        lock_path = os.path.join(Paths.BUNDLE_DIR, "assets", "icon_lock.svg")
        if os.path.exists(lock_path):
            self.lock_overlay.setPixmap(QIcon(lock_path).pixmap(48, 48))
        self.lock_overlay.setStyleSheet("background: transparent;")
        self.lock_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)  # Prevent blocking panning
        self.lock_overlay.hide()

        # --- FLOATING HUD OVERLAY ---
        self.hud_label = QLabel(self)
        self.hud_label.setStyleSheet("""
            background-color: rgba(20, 22, 28, 220);
            color: #f1f5f9;
            border: 1px solid #3a4052;
            border-radius: 12px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: bold;
        """)
        self.hud_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hud_label.hide()
        self.hud_timer = QTimer(self)
        self.hud_timer.setSingleShot(True)
        self.hud_timer.timeout.connect(self.hud_label.hide)

        self.cv_img = None
        self.mask = None
        self.setMouseTracking(True)
        self.update_cursor_visuals()

        # --- WELCOME EMPTY STATE OVERLAY ---
        self.welcome_overlay = WelcomeOverlay(self)
        self.welcome_overlay.open_image_requested.connect(self.open_image_requested.emit)
        self.welcome_overlay.open_folder_requested.connect(self.open_folder_requested.emit)
        self.welcome_overlay.show()

        # --- NAVIGATOR MINIMAP OVERLAY ---
        self.minimap = MinimapWidget(self)
        self.minimap.pan_requested.connect(self._center_on_normalized)
        self.is_minimap_enabled = UserPrefs.load("show_minimap", True, type=bool)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.update_minimap())
        self.verticalScrollBar().valueChanged.connect(lambda _: self.update_minimap())

    def show_hud(self, text: str, duration: int = 800):
        """Displays transient HUD indicator centered near bottom of canvas"""
        self.hud_label.setText(text)
        self.hud_label.adjustSize()
        self.hud_label.move((self.width() - self.hud_label.width()) // 2, self.height() - self.hud_label.height() - 25)
        self.hud_label.show()
        self.hud_timer.start(duration)

    def center_welcome_overlay(self):
        """Centers the welcome card in the visible viewport."""
        if hasattr(self, 'welcome_overlay') and self.welcome_overlay:
            self.welcome_overlay.adjustSize()
            x = max(10, (self.width() - self.welcome_overlay.width()) // 2)
            y = max(10, (self.height() - self.welcome_overlay.height()) // 2)
            self.welcome_overlay.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'welcome_overlay') and self.welcome_overlay.isVisible():
            self.center_welcome_overlay()

    def resizeEvent(self, event):
        """Keep the lock overlay, HUD, and welcome overlay positioned appropriately"""
        super().resizeEvent(event)
        self.lock_overlay.move(self.width() - self.lock_overlay.width() - 20, 20)
        if self.hud_label.isVisible():
            self.hud_label.move((self.width() - self.hud_label.width()) // 2, self.height() - self.hud_label.height() - 25)
        if hasattr(self, 'welcome_overlay') and self.welcome_overlay.isVisible():
            self.center_welcome_overlay()
        if hasattr(self, 'minimap'):
            self.minimap.move(self.width() - self.minimap.width() - 16, self.height() - self.minimap.height() - 16)
            self.update_minimap()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
        paths = [
            u.toLocalFile() for u in event.mimeData().urls()
            if u.isLocalFile() and u.toLocalFile().lower().endswith(valid_exts)
        ]
        if paths:
            event.acceptProposedAction()
            self.images_dropped.emit(paths)
        else:
            event.ignore()

    def set_locked(self, locked: bool):
        """Toggles the lock state and manages the visual cursor & overlay"""
        self.is_locked = locked
        if locked:
            self.cursor_item.hide()
            self.lock_overlay.show()
            self.viewport().unsetCursor() # Ensure native cursor is unhidden while locked
        else:
            self.lock_overlay.hide()
            # Restore the proper cursor for whichever tool is currently equipped
            if self.current_tool in ["BRUSH", "ERASER"]:
                self.viewport().setCursor(Qt.BlankCursor)
                self.cursor_item.show()
            elif self.current_tool in ["RECT", "LASSO", "POLY", "BUCKET"]:
                self.viewport().setCursor(Qt.CrossCursor)
            else:
                self.viewport().unsetCursor()

    def drawBackground(self, painter, rect):
        painter.save()
        painter.resetTransform()
        painter.fillRect(self.viewport().rect(), QColor(38, 38, 38))
        painter.restore()

        # Draw the non-scaling checkerboard strictly behind the image bounds
        if self.cv_img is not None:
            painter.save()
            painter.setClipRect(self.sceneRect()) # Clip rendering to the image's boundaries
            painter.resetTransform()              # Strip the zoom/pan scaling from the painter
            painter.fillRect(self.viewport().rect(), self.backgroundBrush())
            painter.restore()

    def update_cursor_visuals(self):
        if self.current_tool == "ERASER":
            self.cursor_item.setPen(QPen(QColor(56, 189, 248, 220), 1))
            self.cursor_item.setBrush(QBrush(QColor(56, 189, 248, 50)))
        else:
            c = getattr(self, 'current_mask_color', QColor(200, 110, 0, 255))
            self.cursor_item.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 220), 1))
            self.cursor_item.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 50)))
        
        r = self.brush_size / 2
        self.cursor_item.setRect(-r, -r, self.brush_size, self.brush_size)

    def set_brush_size(self, size, show_hud=False):
        size = max(1, min(300, size))
        if self.brush_size != size:
            self.brush_size = size
            self.update_cursor_visuals()
            self.brush_size_changed.emit(self.brush_size)
        if show_hud:
            self.show_hud(f"Brush: {self.brush_size}px")

    def fit_to_screen(self):
        if self.cv_img is not None:
            self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
            curr_pct = int(abs(self.transform().m11()) * 100)
            self.zoom_changed.emit(curr_pct)
            self.show_hud(f"Fit View ({curr_pct}%)")

    def reset_zoom(self):
        self.resetTransform()
        if getattr(self, 'is_flipped_h', False):
            self.scale(-1, 1)
        self.zoom_changed.emit(100)
        self.show_hud("Actual Size (100%)")

    def zoom_by(self, factor):
        self.scale(factor, factor)
        curr_pct = int(abs(self.transform().m11()) * 100)
        self.zoom_changed.emit(curr_pct)
        self.show_hud(f"Zoom: {curr_pct}%")

    def toggle_flip_horizontal(self):
        self.is_flipped_h = not getattr(self, 'is_flipped_h', False)
        self.scale(-1, 1)
        self.show_hud("Flipped View" if self.is_flipped_h else "Normal View")

    def show_comparison(self, show_orig: bool):
        if self.orig_img is None or self.cv_img is None:
            return
        if getattr(self, 'is_comparing', False) == show_orig:
            return
        self.is_comparing = show_orig
        target_img = self.orig_img if show_orig else self.cv_img
        h, w = target_img.shape[:2]
        if len(target_img.shape) == 3 and target_img.shape[2] == 4:
            q_img = QImage(target_img.data, w, h, w * 4, QImage.Format_RGBA8888)
        else:
            q_img = QImage(target_img.data, w, h, w * 3, QImage.Format_RGB888)
        self.image_item.setPixmap(QPixmap.fromImage(q_img))
        if show_orig:
            self.mask_item.hide()
            self.show_hud("Original Scan (Compare)", duration=1500)
        else:
            self.mask_item.show()
            self.show_hud("Restored View", duration=600)

    def set_image(self, cv_img, orig_img=None):
        self.cv_img = cv_img
        if hasattr(self, 'welcome_overlay') and self.welcome_overlay:
            self.welcome_overlay.hide()

        if orig_img is not None:
            self.orig_img = orig_img.copy()
        elif self.orig_img is None:
            self.orig_img = cv_img.copy()

        self.last_drawn_pt = None # Reset straight line anchor on new image
        self.poly_points.clear()
        self.preview_item.setPath(QPainterPath())
        
        h, w = cv_img.shape[:2]
        # Support RGBA rendering if transparency is present
        if len(cv_img.shape) == 3 and cv_img.shape[2] == 4:
            q_img = QImage(cv_img.data, w, h, w*4, QImage.Format_RGBA8888)
        else:
            q_img = QImage(cv_img.data, w, h, w*3, QImage.Format_RGB888)
        self.image_item.setPixmap(QPixmap.fromImage(q_img))
        self.mask = QImage(w, h, QImage.Format_ARGB32)
        self.mask.fill(Qt.transparent)
        self.update_mask_display()
        self.scene.setSceneRect(0, 0, w, h)
        if hasattr(self, 'minimap'):
            self.minimap.set_image(self.image_item.pixmap())
            self.update_minimap()

    def clear_image(self):
        """Clears current image and displays the welcome overlay."""
        self.cv_img = None
        self.orig_img = None
        self.image_item.setPixmap(QPixmap())
        self.mask_item.setPixmap(QPixmap())
        self.cursor_item.hide()
        if hasattr(self, 'minimap'):
            self.minimap.set_image(None)
            self.minimap.hide()
        if hasattr(self, 'welcome_overlay') and self.welcome_overlay:
            self.welcome_overlay.show()
            self.center_welcome_overlay()

    def update_mask_display(self):
        if self.mask: self.mask_item.setPixmap(QPixmap.fromImage(self.mask))

    def apply_bucket_fill(self, pt, is_erasing):
        x, y = int(pt.x()), int(pt.y())
        h, w = self.mask.height(), self.mask.width()
        
        # Guard against clicks physically outside the image bounds
        if not (0 <= x < w and 0 <= y < h): return
        
        # Read the raw 32-bit ARGB data and safely copy it into a NumPy array
        ptr = self.mask.bits()
        mask_np = np.frombuffer(ptr, np.uint8).reshape((h, w, 4)).copy()
        
        # The .copy() forces NumPy to create a strictly contiguous memory array
        alpha = mask_np[:, :, 3].copy() 
        
        fill_val = 0 if is_erasing else 255
        target_val = int(alpha[y, x])
        
        # Abort if the user clicks a pixel that is already exactly the target state
        if target_val == fill_val:
            return
            
        # Create a strict boundary mask for cv2.floodFill (size h+2, w+2)
        # OpenCV treats any non-zero pixel in this mask as an impassable wall.
        ff_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        
        if is_erasing:
            # Erase mode: Wall is empty space. Flood across all semi-transparent pixels up to 0.
            ff_mask[1:-1, 1:-1] = (alpha == 0).astype(np.uint8)
        else:
            # Fill mode: Wall is the solid core of the brush. Flood across everything up to 255.
            ff_mask[1:-1, 1:-1] = (alpha == 255).astype(np.uint8)
            
        # Extreme tolerances (255) to ignore gradients, bounded entirely by our custom wall
        flags = 4 | (255 << 8)
        cv2.floodFill(alpha, ff_mask, (x, y), fill_val, loDiff=255, upDiff=255, flags=flags)
        
        # Safely map the contiguous block back into the RGBA matrix
        mask_np[:, :, 3] = alpha
        
        if not is_erasing:
            # Color newly filled areas to the signature GUI Red
            mask_np[:, :, 0] = 0
            mask_np[:, :, 1] = 0
            mask_np[:, :, 2] = 255
            
        # Write back to QImage architecture
        self.mask = QImage(mask_np.data, w, h, w * 4, QImage.Format_ARGB32).copy()
        self.update_mask_display()

    def wheelEvent(self, event):
        modifiers = event.modifiers()
        
        # Get the scroll delta (some OSs map Alt/Shift to horizontal X axis automatically)
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.angleDelta().x()
            
        if delta == 0:
            return

        if (modifiers & Qt.ControlModifier) or (modifiers & Qt.AltModifier):
            # Ctrl + Scroll or Alt + Scroll = Zoom In/Out anchored to mouse cursor
            zoom = 1.25 if delta > 0 else 0.8
            self.scale(zoom, zoom)
            curr_pct = int(abs(self.transform().m11()) * 100)
            self.zoom_changed.emit(curr_pct)
            self.show_hud(f"Zoom: {curr_pct}%")
            event.accept()
        elif modifiers & Qt.ShiftModifier:
            # Shift + Scroll = Pan Left/Right
            h_bar = self.horizontalScrollBar()
            h_bar.setValue(h_bar.value() - delta)
            event.accept()
        else:
            # Default Scroll = Pan Up/Down
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        # Dynamic Brush Resize: Alt + Right-Click Drag
        if (event.modifiers() & Qt.AltModifier) and event.button() == Qt.RightButton and self.current_tool in ["BRUSH", "ERASER"]:
            self.is_resizing_brush = True
            self.resize_start_pos = event.pos()
            self.resize_start_size = self.brush_size
            self.resize_start_cursor_pos = QCursor.pos() # Save global mouse position to teleport back
            event.accept()
            return

        # Middle Mouse Button Pan: standard editor hand-drag
        if event.button() == Qt.MiddleButton:
            self.is_middle_panning = True
            self.middle_pan_start = event.pos()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        # Always allow moving/panning regardless of lock state
        if self.current_tool == "NONE" or event.button() == Qt.RightButton:
            if event.button() == Qt.RightButton and self.current_tool == "POLY":
                # Right-click instantly cancels an active polygonal selection
                self.poly_points.clear()
                self.preview_item.setPath(QPainterPath())
            super().mousePressEvent(event)
            
        elif self.is_locked:
            # If the mask is locked by AI, silently reject all drawing inputs
            return
            
        elif event.button() == Qt.LeftButton and self.mask:
            curr_pt = self.mapToScene(event.pos())

            # BUCKET TOOL LOGIC
            if self.current_tool == "BUCKET":
                self.mask_changed.emit()
                is_erasing = bool(event.modifiers() & Qt.AltModifier)
                self.apply_bucket_fill(curr_pt, is_erasing)
                return
            
            # Single-click interaction exclusively for Poly selection construction
            if self.current_tool == "POLY":
                if not self.poly_points:
                    self.mask_changed.emit() # Save state before we start adding nodes!
                self.poly_points.append(curr_pt)
                self.mouseMoveEvent(event) # Force preview update to snap visual line immediately
                return
            
            # Standard drawing initializations
            self.mask_changed.emit()
            self.is_drawing = True
            
            is_brush_tool = self.current_tool in ["BRUSH", "ERASER"]
            
            # Photoshop Shift+Click Straight Line Feature
            if is_brush_tool and (event.modifiers() & Qt.ShiftModifier) and self.last_drawn_pt is not None:
                self.paint_mask_stroke(self.last_drawn_pt, curr_pt)
                self.last_pt = curr_pt
                self.last_drawn_pt = curr_pt
            else:
                self.start_pt = curr_pt
                self.last_pt = curr_pt
                
                if self.current_tool == "LASSO": 
                    self.lasso_path = QPainterPath(self.start_pt)
                elif is_brush_tool:
                    # Instantly paint a dot on a single click without needing to move
                    self.paint_mask_stroke(curr_pt, curr_pt)
                    self.last_drawn_pt = curr_pt

    def mouseMoveEvent(self, event):
        # Handle Middle Mouse Button Panning
        if getattr(self, 'is_middle_panning', False):
            delta = event.pos() - self.middle_pan_start
            self.middle_pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        # Handle dynamic brush resizing motion
        if self.is_resizing_brush:
            delta_x = event.pos().x() - self.resize_start_pos.x()
            new_size = int(self.resize_start_size + delta_x * 0.5) # Scale sensitivity factor
            new_size = max(1, min(300, new_size)) # Clamp within slider limits (1 to 300)
            self.set_brush_size(new_size, show_hud=True)
            event.accept()
            return

        curr_pt = self.mapToScene(event.pos())
        self.cursor_item.setPos(curr_pt)
        self.mouse_moved.emit(int(curr_pt.x()), int(curr_pt.y()))
        
        # Always update Polygonal preview line connecting to the cursor dynamically
        if self.current_tool == "POLY" and self.poly_points:
            is_erasing = bool(event.modifiers() & Qt.AltModifier)
            p_color = QColor(56, 189, 248, 200) if is_erasing else getattr(self, 'current_mask_color', QColor(200, 110, 0, 200))
            self.preview_item.setPen(QPen(p_color, 2, Qt.DashLine))

            path = QPainterPath()
            path.moveTo(self.poly_points[0])
            for pt in self.poly_points[1:]:
                path.lineTo(pt)
            path.lineTo(curr_pt) # Track cursor
            self.preview_item.setPath(path)

        if self.is_drawing:
            if self.current_tool in ["BRUSH", "ERASER"]:
                self.paint_mask_stroke(self.last_pt, curr_pt)
                self.last_pt = curr_pt
                self.last_drawn_pt = curr_pt
            elif self.current_tool in ["RECT", "LASSO"]:
                # Dynamically change preview color if Alt is held down!
                is_erasing = bool(event.modifiers() & Qt.AltModifier)
                p_color = QColor(56, 189, 248, 200) if is_erasing else getattr(self, 'current_mask_color', QColor(200, 110, 0, 200))
                self.preview_item.setPen(QPen(p_color, 2, Qt.DashLine))

                if self.current_tool == "RECT":
                    path = QPainterPath()
                    path.addRect(QRectF(self.start_pt, curr_pt).normalized())
                    self.preview_item.setPath(path)
                elif self.current_tool == "LASSO":
                    self.lasso_path.lineTo(curr_pt)
                    self.preview_item.setPath(self.lasso_path)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and getattr(self, 'is_middle_panning', False):
            self.is_middle_panning = False
            self.set_locked(self.is_locked)
            event.accept()
            return

        if self.is_resizing_brush and event.button() == Qt.RightButton:
            self.is_resizing_brush = False
            if self.resize_start_cursor_pos:
                QCursor.setPos(self.resize_start_cursor_pos) # Teleport mouse back!
            event.accept()
            return

        if self.is_drawing:
            curr_pt = self.mapToScene(event.pos())
            is_erasing = bool(event.modifiers() & Qt.AltModifier)
            if self.current_tool == "RECT": self.paint_mask_rect(self.start_pt, curr_pt, is_erasing)
            elif self.current_tool == "LASSO": self.paint_mask_lasso(is_erasing)
            self.is_drawing = False
            self.preview_item.setPath(QPainterPath())
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.current_tool == "POLY":
            if len(self.poly_points) >= 3:
                is_erasing = bool(event.modifiers() & Qt.AltModifier)
                
                path = QPainterPath()
                path.moveTo(self.poly_points[0])
                for pt in self.poly_points[1:]:
                    path.lineTo(pt)
                path.closeSubpath()
                
                painter, color = self.get_painter(is_erasing)
                painter.fillPath(path, QBrush(color))
                painter.end()
                self.update_mask_display()
                
            self.poly_points.clear()
            self.preview_item.setPath(QPainterPath())
            return
        super().mouseDoubleClickEvent(event)

    def create_context_menu(self) -> QMenu:
        w = self.window()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Config.COLOR_PANEL};
                color: {Config.COLOR_TEXT};
                border: 1px solid {Config.COLOR_BORDER_SUBTLE};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px 6px 12px;
                border-radius: 3px;
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background-color: {Config.COLOR_ACCENT};
                color: #ffffff;
            }}
            QMenu::item:disabled {{
                color: {Config.COLOR_TEXT_DIM};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {Config.COLOR_BORDER_SUBTLE};
                margin: 4px 8px;
            }}
        """)

        has_img = self.cv_img is not None
        can_undo = hasattr(w, 'history') and w.history.can_undo()
        can_redo = hasattr(w, 'history') and w.history.can_redo()
        not_locked = not getattr(self, 'is_locked', False)

        act_undo = menu.addAction("Undo")
        act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        act_undo.setEnabled(can_undo and not_locked)
        if hasattr(w, 'on_undo'):
            act_undo.triggered.connect(w.on_undo)

        act_redo = menu.addAction("Redo")
        act_redo.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        act_redo.setEnabled(can_redo and not_locked)
        if hasattr(w, 'on_redo'):
            act_redo.triggered.connect(w.on_redo)

        menu.addSeparator()

        act_clear = menu.addAction("Clear Mask")
        act_clear.setShortcut(QKeySequence("Ctrl+D"))
        act_clear.setEnabled(has_img and not_locked)
        act_clear.triggered.connect(self.clear_mask)

        act_invert = menu.addAction("Invert Mask")
        act_invert.setShortcut(QKeySequence("Ctrl+Shift+I"))
        act_invert.setEnabled(has_img and not_locked)
        act_invert.triggered.connect(self.invert_mask)

        act_expand = menu.addAction("Expand Mask (+3px)")
        act_expand.setShortcut(QKeySequence("Shift+>"))
        act_expand.setEnabled(has_img and not_locked)
        act_expand.triggered.connect(lambda: self.dilate_mask(3))

        act_contract = menu.addAction("Contract Mask (-3px)")
        act_contract.setShortcut(QKeySequence("Shift+<"))
        act_contract.setEnabled(has_img and not_locked)
        act_contract.triggered.connect(lambda: self.erode_mask(3))

        menu.addSeparator()

        act_ocr = menu.addAction("OCR Scan")
        act_ocr.setShortcut(QKeySequence("O"))
        act_ocr.setEnabled(has_img and not_locked)
        if hasattr(w, 'on_ocr_scan'):
            act_ocr.triggered.connect(w.on_ocr_scan)

        act_clean = menu.addAction("Execute Clean")
        act_clean.setShortcut(QKeySequence("C"))
        act_clean.setEnabled(has_img and not_locked)
        if hasattr(w, 'on_lama_clean'):
            act_clean.triggered.connect(w.on_lama_clean)

        menu.addSeparator()

        act_fit = menu.addAction("Fit to Screen")
        act_fit.setShortcut(QKeySequence("Ctrl+0"))
        act_fit.setEnabled(has_img)
        act_fit.triggered.connect(self.fit_to_screen)

        act_actual = menu.addAction("Actual Size (100%)")
        act_actual.setShortcut(QKeySequence("Ctrl+1"))
        act_actual.setEnabled(has_img)
        act_actual.triggered.connect(self.reset_zoom)

        return menu

    def contextMenuEvent(self, event):
        # Do not show context menu if in polygon construction (right-click cancels poly) or resizing brush
        if self.current_tool == "POLY" and self.poly_points:
            event.accept()
            return
        if getattr(self, 'is_resizing_brush', False):
            event.accept()
            return

        menu = self.create_context_menu()
        menu.exec(event.globalPos())
        event.accept()

    def update_minimap(self):
        if not hasattr(self, 'minimap') or not getattr(self, 'is_minimap_enabled', True):
            if hasattr(self, 'minimap'):
                self.minimap.hide()
            return

        if self.cv_img is None:
            self.minimap.hide()
            return

        h, w = self.cv_img.shape[:2]
        if w <= 0 or h <= 0:
            self.minimap.hide()
            return

        vp_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        norm_x = vp_rect.x() / w
        norm_y = vp_rect.y() / h
        norm_w = vp_rect.width() / w
        norm_h = vp_rect.height() / h

        norm_rect = QRectF(norm_x, norm_y, norm_w, norm_h)
        self.minimap.set_viewport_rect(norm_rect)
        self.minimap.move(self.width() - self.minimap.width() - 16, self.height() - self.minimap.height() - 16)
        self.minimap.show()

    def _center_on_normalized(self, norm_x: float, norm_y: float):
        if self.cv_img is None:
            return
        h, w = self.cv_img.shape[:2]
        scene_x = norm_x * w
        scene_y = norm_y * h
        self.centerOn(scene_x, scene_y)
        self.update_minimap()

    def toggle_minimap(self):
        self.is_minimap_enabled = not getattr(self, 'is_minimap_enabled', True)
        UserPrefs.save("show_minimap", self.is_minimap_enabled)
        if self.is_minimap_enabled:
            self.update_minimap()
            self.show_hud("Minimap: Shown")
        else:
            self.minimap.hide()
            self.show_hud("Minimap: Hidden")
        top_w = self.window()
        if hasattr(top_w, 'act_minimap'):
            top_w.act_minimap.setChecked(self.is_minimap_enabled)

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
            self.images_dropped.emit(paths)
        else:
            event.ignore()

    def cycle_mask_color(self):
        """Cycles through mask overlay color presets (Coral Red, Teal Cyan, Lime Green)"""
        self.mask_color_idx = (self.mask_color_idx + 1) % len(self.mask_colors)
        self.current_mask_color = self.mask_colors[self.mask_color_idx]
        name = self.mask_color_names[self.mask_color_idx]
        self.update_cursor_visuals()

        # If active mask exists, recolor existing mask pixels
        if self.mask is not None:
            h, w = self.mask.height(), self.mask.width()
            ptr = self.mask.bits()
            mask_np = np.frombuffer(ptr, np.uint8).reshape((h, w, 4)).copy()
            alpha = mask_np[:, :, 3]
            active_idx = alpha > 0
            if np.any(active_idx):
                mask_np[active_idx, 0] = self.current_mask_color.blue()
                mask_np[active_idx, 1] = self.current_mask_color.green()
                mask_np[active_idx, 2] = self.current_mask_color.red()
                self.mask = QImage(mask_np.data, w, h, w * 4, QImage.Format_ARGB32).copy()
                self.update_mask_display()

        self.show_hud(f"Mask Color: {name}")

    def dilate_mask(self, px=3):
        """Expands the mask boundary outward by px pixels using circular dilation"""
        if self.mask is None or self.is_locked: return
        h, w = self.mask.height(), self.mask.width()
        ptr = self.mask.bits()
        mask_np = np.frombuffer(ptr, np.uint8).reshape((h, w, 4)).copy()
        alpha = mask_np[:, :, 3].copy()
        if not np.any(alpha): return

        self.mask_changed.emit()
        k_size = px * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        dilated = cv2.dilate(alpha, kernel)

        c = getattr(self, 'current_mask_color', QColor(200, 110, 0, 255))
        mask_np[:, :, 0] = c.blue()
        mask_np[:, :, 1] = c.green()
        mask_np[:, :, 2] = c.red()
        mask_np[:, :, 3] = dilated

        self.mask = QImage(mask_np.data, w, h, w * 4, QImage.Format_ARGB32).copy()
        self.update_mask_display()
        self.show_hud(f"Grow Mask (+{px}px)")

    def erode_mask(self, px=3):
        """Contracts the mask boundary inward by px pixels using circular erosion"""
        if self.mask is None or self.is_locked: return
        h, w = self.mask.height(), self.mask.width()
        ptr = self.mask.bits()
        mask_np = np.frombuffer(ptr, np.uint8).reshape((h, w, 4)).copy()
        alpha = mask_np[:, :, 3].copy()
        if not np.any(alpha): return

        self.mask_changed.emit()
        k_size = px * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        eroded = cv2.erode(alpha, kernel)

        c = getattr(self, 'current_mask_color', QColor(200, 110, 0, 255))
        mask_np[:, :, 0] = c.blue()
        mask_np[:, :, 1] = c.green()
        mask_np[:, :, 2] = c.red()
        mask_np[:, :, 3] = eroded

        self.mask = QImage(mask_np.data, w, h, w * 4, QImage.Format_ARGB32).copy()
        self.update_mask_display()
        self.show_hud(f"Shrink Mask (-{px}px)")

    def invert_mask(self):
        """Inverts the current mask alpha values"""
        if self.mask is None or self.is_locked: return
        h, w = self.mask.height(), self.mask.width()
        ptr = self.mask.bits()
        mask_np = np.frombuffer(ptr, np.uint8).reshape((h, w, 4)).copy()
        alpha = mask_np[:, :, 3].copy()

        self.mask_changed.emit()
        inverted = 255 - alpha

        c = getattr(self, 'current_mask_color', QColor(200, 110, 0, 255))
        mask_np[:, :, 0] = c.blue()
        mask_np[:, :, 1] = c.green()
        mask_np[:, :, 2] = c.red()
        mask_np[:, :, 3] = inverted

        self.mask = QImage(mask_np.data, w, h, w * 4, QImage.Format_ARGB32).copy()
        self.update_mask_display()
        self.show_hud("Invert Mask")

    def toggle_quick_mask(self):
        """Temporarily toggles mask visibility without deleting selection"""
        self.is_mask_hidden = not getattr(self, 'is_mask_hidden', False)
        if self.is_mask_hidden:
            self.mask_item.hide()
            self.show_hud("Mask Hidden [Q]")
        else:
            self.mask_item.show()
            self.show_hud("Mask Visible [Q]")

    def get_painter(self, force_erase=False):
        painter = QPainter(self.mask)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.current_tool == "ERASER" or force_erase:
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            color = Qt.transparent
        else:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            color = getattr(self, 'current_mask_color', QColor(200, 110, 0, 255))
            
        return painter, color

    def paint_mask_stroke(self, p1, p2):
        painter, color = self.get_painter()
        painter.setPen(QPen(color, self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if p1 == p2:
            painter.drawPoint(p1)
        else:
            painter.drawLine(p1, p2)
        painter.end()
        self.update_mask_display()

    def paint_mask_rect(self, p1, p2, is_erasing=False):
        painter, color = self.get_painter(is_erasing)
        painter.fillRect(QRectF(p1, p2).normalized(), QBrush(color))
        painter.end()
        self.update_mask_display()

    def paint_mask_lasso(self, is_erasing=False):
        painter, color = self.get_painter(is_erasing)
        painter.fillPath(self.lasso_path, QBrush(color))
        painter.end()
        self.update_mask_display()

    def set_mask_opacity(self, opacity_percent):
        # Purely cosmetic: Adjusts the UI layer visibility, leaving math matrix intact
        if self.mask_item:
            self.mask_item.setOpacity(opacity_percent / 100.0)

    def reset_mask(self):
        """Programmatically clears mask pixels WITHOUT emitting mask_changed (avoids history push)."""
        self.poly_points.clear()
        if hasattr(self, 'preview_item') and self.preview_item:
            self.preview_item.setPath(QPainterPath())
        if self.mask:
            self.mask.fill(Qt.transparent)
            self.update_mask_display()
            self.last_drawn_pt = None

    def clear_mask(self):
        if self.is_locked: return  # Block clearing if AI is working
        self.poly_points.clear()
        self.preview_item.setPath(QPainterPath())
        if self.mask:
            self.mask_changed.emit()
            self.mask.fill(Qt.transparent)
            self.update_mask_display()
            self.last_drawn_pt = None # Reset anchor when mask is explicitly cleared
