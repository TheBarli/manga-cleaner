import os
import cv2
from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, 
                             QGraphicsPathItem, QGraphicsEllipseItem, QLabel)
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush, QPainterPath, QIcon, QCursor
from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QTimer
import numpy as np
from src.utils.paths import Paths

#/////////////////////////////////#
#   MULTI-TOOL CANVAS ENGINE      #
#/////////////////////////////////#

class MangaCanvas(QGraphicsView):
    mask_changed = Signal()
    brush_size_changed = Signal(int)

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

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

        self.last_pt = QPointF()
        self.start_pt = QPointF()
        self.last_drawn_pt = None # Remembers position for Shift+Click straight lines
        self.lasso_path = QPainterPath()
        self.poly_points = []
        self.preview_item = QGraphicsPathItem()
        self.preview_item.setPen(QPen(QColor(244, 63, 94, 200), 2, Qt.DashLine)) # Modern coral red
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

    def show_hud(self, text: str, duration: int = 800):
        """Displays transient HUD indicator centered near bottom of canvas"""
        self.hud_label.setText(text)
        self.hud_label.adjustSize()
        self.hud_label.move((self.width() - self.hud_label.width()) // 2, self.height() - self.hud_label.height() - 25)
        self.hud_label.show()
        self.hud_timer.start(duration)

    def resizeEvent(self, event):
        """Keep the lock overlay and HUD positioned appropriately"""
        super().resizeEvent(event)
        self.lock_overlay.move(self.width() - self.lock_overlay.width() - 20, 20)
        if self.hud_label.isVisible():
            self.hud_label.move((self.width() - self.hud_label.width()) // 2, self.height() - self.hud_label.height() - 25)

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
        painter.fillRect(self.viewport().rect(), QColor(13, 14, 18))
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
            self.cursor_item.setPen(QPen(QColor(244, 63, 94, 220), 1))
            self.cursor_item.setBrush(QBrush(QColor(244, 63, 94, 50)))
        
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
            self.show_hud(f"Fit View ({curr_pct}%)")

    def reset_zoom(self):
        self.resetTransform()
        if getattr(self, 'is_flipped_h', False):
            self.scale(-1, 1)
        self.show_hud("Actual Size (100%)")

    def zoom_by(self, factor):
        self.scale(factor, factor)
        curr_pct = int(abs(self.transform().m11()) * 100)
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
        
        # Always update Polygonal preview line connecting to the cursor dynamically
        if self.current_tool == "POLY" and self.poly_points:
            is_erasing = bool(event.modifiers() & Qt.AltModifier)
            p_color = QColor(56, 189, 248, 200) if is_erasing else QColor(244, 63, 94, 200)
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
                p_color = QColor(56, 189, 248, 200) if is_erasing else QColor(244, 63, 94, 200)
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

    def get_painter(self, force_erase=False):
        painter = QPainter(self.mask)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.current_tool == "ERASER" or force_erase:
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            color = Qt.transparent
        else:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            color = QColor(255, 0, 0, 255)
            
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

    def clear_mask(self):
        if self.is_locked: return  # Block clearing if AI is working
        self.poly_points.clear()
        self.preview_item.setPath(QPainterPath())
        if self.mask:
            self.mask_changed.emit()
            self.mask.fill(Qt.transparent)
            self.update_mask_display()
            self.last_drawn_pt = None # Reset anchor when mask is explicitly cleared
