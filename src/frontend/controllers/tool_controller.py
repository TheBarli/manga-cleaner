from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence, QPainterPath
from PySide6.QtWidgets import QGraphicsView
from src.utils.config import Config


#/////////////////////////////////#
#       TOOL CONTROLLER           #
#/////////////////////////////////#

class ToolController:
    """Manages active tool states, canvas interaction modes, shortcuts, and brush resizing."""

    def __init__(self, window):
        self.window = window
        self.is_alt_erasing = False
        self.is_alt_brushing = False
        self.is_space_moving = False
        self.pre_space_tool = "NONE"

    def setup_shortcuts(self):
        """Initializes global keyboard shortcuts for tools, AI triggers, brush resizing, and navigation."""
        w = self.window

        # Single-key Tool Selectors
        QShortcut(QKeySequence("B"), w).activated.connect(lambda: self.set_tool("BRUSH"))
        QShortcut(QKeySequence("E"), w).activated.connect(lambda: self.set_tool("ERASER"))
        QShortcut(QKeySequence("R"), w).activated.connect(lambda: self.set_tool("RECT"))
        QShortcut(QKeySequence("L"), w).activated.connect(lambda: self.set_tool("LASSO"))
        QShortcut(QKeySequence("P"), w).activated.connect(lambda: self.set_tool("POLY"))
        QShortcut(QKeySequence("G"), w).activated.connect(lambda: self.set_tool("BUCKET"))
        QShortcut(QKeySequence("M"), w).activated.connect(lambda: self.set_tool("NONE"))
        
        # AI & Detection Operations
        QShortcut(QKeySequence("O"), w).activated.connect(w.on_ocr_scan)
        QShortcut(QKeySequence("T"), w).activated.connect(w.on_transparency_scan)
        QShortcut(QKeySequence("C"), w).activated.connect(w.on_lama_clean)

        # Dynamic Brush Resize Brackets
        QShortcut(QKeySequence("["), w).activated.connect(lambda: self.adjust_brush_size(-5))
        QShortcut(QKeySequence("]"), w).activated.connect(lambda: self.adjust_brush_size(5))
        QShortcut(QKeySequence("Shift+["), w).activated.connect(lambda: self.adjust_brush_size(-20))
        QShortcut(QKeySequence("Shift+]"), w).activated.connect(lambda: self.adjust_brush_size(20))

        # Rapid Page Navigation
        QShortcut(QKeySequence(Qt.Key_PageDown), w).activated.connect(lambda: w.navigate_file(1))
        QShortcut(QKeySequence(Qt.Key_PageUp), w).activated.connect(lambda: w.navigate_file(-1))
        QShortcut(QKeySequence("Ctrl+Right"), w).activated.connect(lambda: w.navigate_file(1))
        QShortcut(QKeySequence("Ctrl+Left"), w).activated.connect(lambda: w.navigate_file(-1))
        QShortcut(QKeySequence("Alt+Right"), w).activated.connect(lambda: w.navigate_file(1))
        QShortcut(QKeySequence("Alt+Left"), w).activated.connect(lambda: w.navigate_file(-1))



    def adjust_brush_size(self, delta: int):
        """Adjusts the brush size on the canvas clamped between 1 and 300px."""
        new_size = max(1, min(300, self.window.canvas.brush_size + delta))
        self.window.canvas.set_brush_size(new_size, show_hud=True)

    def handle_key_press(self, event):
        """Handles temporary tool toggles on key press (Alt for eraser/brush, Space for pan, Backslash for comparison)."""
        # Trigger inverse tool temporarily if Alt is held down
        if event.key() == Qt.Key_Alt and not event.isAutoRepeat():
            if self.window.canvas.current_tool == "BRUSH":
                self.is_alt_erasing = True
                self.set_tool("ERASER")
            elif self.window.canvas.current_tool == "ERASER":
                self.is_alt_brushing = True
                self.set_tool("BRUSH")
                
        # Trigger Move temporarily if Space is held down
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if not self.is_space_moving:
                self.is_space_moving = True
                self.pre_space_tool = self.window.canvas.current_tool
                self.set_tool("NONE")

        # Hold Backslash to Compare with Original Scan
        if event.key() == Qt.Key_Backslash and not event.isAutoRepeat():
            self.window.canvas.show_comparison(True)

    def handle_key_release(self, event):
        """Restores previous tool state on key release."""
        # Release Backslash to return to cleaned/current view
        if event.key() == Qt.Key_Backslash and not event.isAutoRepeat():
            self.window.canvas.show_comparison(False)

        # Snap back to opposite tool when Alt is released
        if event.key() == Qt.Key_Alt and not event.isAutoRepeat():
            if self.is_alt_erasing:
                self.is_alt_erasing = False
                if self.window.canvas.current_tool == "ERASER":
                    self.set_tool("BRUSH")
            elif self.is_alt_brushing:
                self.is_alt_brushing = False
                if self.window.canvas.current_tool == "BRUSH":
                    self.set_tool("ERASER")
                    
        # Snap back to previous tool when Space is released
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if self.is_space_moving:
                self.is_space_moving = False
                if self.window.canvas.current_tool == "NONE":
                    self.set_tool(self.pre_space_tool)

    def set_tool(self, tool: str):
        """Activates a tool, updates canvas drag modes, cursor visuals, sidebar buttons, and status labels."""
        # Prevent dangling poly lines if user swaps tools mid-selection
        if self.window.canvas.current_tool == "POLY" and tool != "POLY":
            self.window.canvas.poly_points.clear()
            self.window.canvas.preview_item.setPath(QPainterPath())

        self.window.canvas.current_tool = tool
        for btn in self.window.tools.buttons.values(): 
            btn.setChecked(False)
        
        # Ensure correct visual cursor state
        self.window.canvas.update_cursor_visuals()
        
        if tool == "NONE":
            self.window.canvas.setDragMode(QGraphicsView.ScrollHandDrag)
            self.window.canvas.viewport().unsetCursor()
            self.window.canvas.cursor_item.hide()
            self.window.tools.buttons["MOVE"].setChecked(True)
            self.window.mode_lbl.setText("MODE: MOVING")
            self.window.mode_lbl.setProperty("state", "dim")
            self.window.mode_lbl.style().unpolish(self.window.mode_lbl)
            self.window.mode_lbl.style().polish(self.window.mode_lbl)
            
        else:
            self.window.canvas.setDragMode(QGraphicsView.NoDrag)
            
            if tool in ["BRUSH", "ERASER"]:
                if not self.window.canvas.is_locked:
                    self.window.canvas.viewport().setCursor(Qt.BlankCursor)
                    self.window.canvas.cursor_item.show()
                else:
                    self.window.canvas.viewport().unsetCursor()
            else:
                if not self.window.canvas.is_locked:
                    self.window.canvas.viewport().setCursor(Qt.CrossCursor)
                else:
                    self.window.canvas.viewport().unsetCursor()
                self.window.canvas.cursor_item.hide()
            
            mapping = {
                "BRUSH": "BRUSH", "ERASER": "ERASER", "RECT": "RECT", 
                "LASSO": "LASSO", "POLY": "POLY", "BUCKET": "BUCKET"
            }
            if tool in mapping: 
                self.window.tools.buttons[mapping[tool]].setChecked(True)
            
            if tool == "ERASER":
                self.window.mode_lbl.setText("MODE: ERASING")
                self.window.mode_lbl.setProperty("state", "erase")
            elif tool == "BUCKET":
                self.window.mode_lbl.setText("MODE: FILLING")
                self.window.mode_lbl.setProperty("state", "normal")
            else:
                self.window.mode_lbl.setText("MODE: PAINTING")
                self.window.mode_lbl.setProperty("state", "normal")
            self.window.mode_lbl.style().unpolish(self.window.mode_lbl)
            self.window.mode_lbl.style().polish(self.window.mode_lbl)

        tool_names = {
            "NONE": "Move",
            "BRUSH": "Brush",
            "ERASER": "Eraser",
            "RECT": "Rectangle",
            "LASSO": "Lasso",
            "POLY": "Polygonal",
            "BUCKET": "Bucket Fill"
        }
        if hasattr(self.window, 'status_tool_lbl'):
            self.window.status_tool_lbl.setText(f"Tool: {tool_names.get(tool, tool.capitalize())}")
