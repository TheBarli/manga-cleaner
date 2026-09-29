import os
import PySide6.QtSvg 
from PySide6.QtWidgets import (QListWidget, QListWidgetItem, QWidget, QVBoxLayout, 
                             QPushButton, QLabel, QFrame, QSlider, QHBoxLayout,
                             QStyledItemDelegate, QGridLayout)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QIcon
from src.utils.config import Config
from src.utils.paths import Paths

#/////////////////////////////////#
#    STUDIO COMPONENT LIBRARY     #
#/////////////////////////////////#

class FileListDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.icons = {}

    def _get_icon(self, state_name: str) -> QIcon:
        """Caches and returns the SVG icon for the given state"""
        if state_name not in self.icons:
            icon_path = os.path.join(Paths.BUNDLE_DIR, "assets", f"icon_{state_name}.svg")
            if os.path.exists(icon_path):
                self.icons[state_name] = QIcon(icon_path)
            else:
                self.icons[state_name] = QIcon() 
        return self.icons[state_name]

    def paint(self, painter, option, index):
        # 1. Paint standard background, highlight, checkbox, and text
        super().paint(painter, option, index)
        
        # 2. Extract our custom status and lock flags
        state_name = index.data(Qt.UserRole + 1)
        is_locked = index.data(Qt.UserRole + 2)
        
        icon_size = 18
        offset_x = 4  # Starting right-margin
        
        # 3. Draw the Status Icon (Far Right)
        if state_name:
            icon = self._get_icon(state_name)
            if not icon.isNull():
                x = option.rect.right() - icon_size - offset_x
                y = option.rect.top() + (option.rect.height() - icon_size) // 2
                rect = QRect(x, y, icon_size, icon_size)
                icon.paint(painter, rect, Qt.AlignCenter, QIcon.Normal, QIcon.On)
                offset_x += icon_size + 4  # Shift cursor left for the next icon
                
        # 4. Draw the Lock Icon (To the left of the status icon)
        if is_locked:
            lock_icon = self._get_icon("lock")
            if not lock_icon.isNull():
                x = option.rect.right() - icon_size - offset_x
                y = option.rect.top() + (option.rect.height() - icon_size) // 2
                rect = QRect(x, y, icon_size, icon_size)
                lock_icon.paint(painter, rect, Qt.AlignCenter, QIcon.Normal, QIcon.On)

class FileListWidget(QListWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background: {Config.COLOR_PANEL}; border: none;")
        self.setItemDelegate(FileListDelegate(self))

    def add_file(self, full_path: str):
        item = QListWidgetItem(os.path.basename(full_path))
        item.setData(Qt.UserRole, full_path)
        item.setData(Qt.UserRole + 1, "unmodified")  
        item.setData(Qt.UserRole + 2, False) # Initial lock state
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)
        self.addItem(item)

    def update_item_state(self, full_path: str, state_name: str):
        for i in range(self.count()):
            item = self.item(i)
            if item.data(Qt.UserRole) == full_path:
                item.setData(Qt.UserRole + 1, state_name)
                break

class ToolGroup(QFrame):
    def __init__(self, title, button_configs):
        super().__init__()
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(5, 5, 5, 5)
        main_lay.setSpacing(4)
        
        lbl = QLabel(title.upper())
        lbl.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 9px; font-weight: bold;")
        main_lay.addWidget(lbl)
        
        grid_lay = QGridLayout()
        grid_lay.setSpacing(4)
        
        self.buttons = {}
        checkable = ["MOVE", "BRUSH", "ERASER", "RECT", "LASSO", "POLY", "BUCKET"]
        
        for i, name in enumerate(button_configs):
            btn = QPushButton(name)
            if name in checkable: 
                btn.setCheckable(True)
                btn.setAutoExclusive(True) 
            self.buttons[name] = btn
            
            # Map index to a 2-column grid (row = index // 2, col = index % 2)
            row = i // 2
            col = i % 2
            grid_lay.addWidget(btn, row, col)
            
        main_lay.addLayout(grid_lay)

class HardwareMonitor(QFrame):
    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        
        self.lbl = QLabel("SYSTEM IDLE")
        self.lbl.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-weight: bold; font-size: 10px;")
        
        self.bar = QSlider(Qt.Horizontal)
        self.bar.setRange(0, 100)
        self.bar.setFixedWidth(100)
        self.bar.setEnabled(False)
        
        lay.addWidget(self.lbl)
        lay.addWidget(self.bar)

class LabeledSlider(QWidget):
    def __init__(self, label, default, minimum, maximum, callback=None, is_tile=False, suffix="px"):
        super().__init__()
        self.is_tile = is_tile
        self.suffix = suffix
        self.base_label = label
        lay = QVBoxLayout(self)
        
        self.display = QLabel("")
        self.display.setStyleSheet(f"color: {Config.COLOR_TEXT_MUTED}; font-size: 10px; font-weight: 500;")
        
        self.slider = QSlider(Qt.Horizontal)
        if is_tile:
            self.slider.setRange(1, 8) 
            self.slider.setValue(default // 512)
        else:
            self.slider.setRange(minimum, maximum)
            self.slider.setValue(default)
            
        self.slider.valueChanged.connect(self.update_text)
        if callback: self.slider.valueChanged.connect(callback)
            
        lay.addWidget(self.display)
        lay.addWidget(self.slider)
        self.update_text(self.slider.value())

    def update_text(self, val):
        if self.is_tile:
            self.display.setText(f"{self.base_label}: {val * 512}px")
        else:
            self.display.setText(f"{self.base_label}: {val}{self.suffix}")
