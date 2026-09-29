import os
import cv2
import numpy as np
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QSplitter, QFileDialog,
                             QMenu, QMessageBox, QGraphicsView, QProgressBar, QInputDialog,
                             QDialog, QComboBox, QDialogButtonBox, QFormLayout, QCheckBox,
                             QStatusBar)
from PySide6.QtGui import QShortcut, QKeySequence, QImage, QPainterPath
from PySide6.QtCore import Qt, QTimer, QThread
from enum import Enum, auto
from src.frontend.widgets import FileListWidget, ToolGroup, LabeledSlider, HardwareMonitor, ToastNotification
from src.frontend.canvas import MangaCanvas
from src.frontend.help_system import HelpSystem
from src.utils.system_info import SystemMonitor
from src.utils.history import HistoryManager
from src.utils.config import Config
from src.utils.paths import Paths
from src.utils.logger import logger
from src.backend.photoshop import PhotoshopBridge
from src.backend.photopea import PhotopeaBridge
from src.backend.batch_engine import BatchEngine
from src.backend.workers import AIWorker, get_pool, _run_flush_process

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
#   STUDIO MAIN CONTROLLER        #
#/////////////////////////////////#

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{Config.APP_NAME} v{Config.VERSION}")
        self.resize(1500, 900)

        self.monitor = SystemMonitor()
        self.history = HistoryManager(Config.MAX_HISTORY)
        self.batch_engine = BatchEngine()
        self.worker_thread = None
        self.is_batching = False
        
        # Tool Toggle States
        self.is_alt_erasing = False 
        self.is_alt_brushing = False 
        self.is_space_moving = False
        self.pre_space_tool = "NONE"
        
        self.current_img_path = None
        self.batch_scan_type = "ocr"
        self.image_sessions = {}
        self.page_states = {}
        self.task_queue = []
        self.total_tasks = 0
        self.completed_tasks = 0
        self.total_lama_tasks = 0
        self.completed_lama_tasks = 0
        
        self.init_ui()
        self.setup_shortcuts()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_telemetry)
        self.timer.start(2000)
        logger.info("--- STUDIO INTERFACE READY ---")

    def init_ui(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        main_lay = QVBoxLayout(self.central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        #/////////////////////////////////#
        #           NAVIGATION            #
        #/////////////////////////////////#
        self.nav = QFrame()
        self.nav.setObjectName("NavBar")
        self.nav.setFixedHeight(60)
        nav_lay = QHBoxLayout(self.nav)
        
        title = QLabel(f"{Config.APP_NAME.upper()} {Config.VERSION}")
        title.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-weight: bold; font-size: 18px;")
        
        self.hw_mon = HardwareMonitor()
        
        btn_help = QPushButton("?")
        btn_help.setFixedSize(30, 30)
        btn_help.clicked.connect(lambda: HelpSystem.show_guide(self))
        
        btn_open = QPushButton("IMPORT FOLDER")
        btn_open.clicked.connect(self.on_open_folder)
        
        self.btn_editor = QPushButton("SEND TO EDITOR ▼")
        ed_menu = QMenu(self)
        
        # Disable Photoshop Button Safely on Linux
        ps_action = ed_menu.addAction("Adobe Photoshop")
        ps_action.triggered.connect(lambda: self.on_editor_bridge("photoshop"))
        if os.name != 'nt':
            ps_action.setEnabled(False)
            ps_action.setText("Adobe Photoshop")
            
        ed_menu.addAction("Photopea (Web)").triggered.connect(lambda: self.on_editor_bridge("photopea"))
        self.btn_editor.setMenu(ed_menu)
        
        self.btn_export = QPushButton("EXPORT ▼")
        self.btn_export.setObjectName("PrimaryBtn")
        exp_menu = QMenu(self)
        exp_menu.addAction("Export as JPG").triggered.connect(lambda: self.on_export("jpg"))
        exp_menu.addAction("Export as PNG").triggered.connect(lambda: self.on_export("png"))
        self.btn_export.setMenu(exp_menu)

        nav_lay.addWidget(title)
        nav_lay.addStretch()
        nav_lay.addWidget(self.hw_mon)
        nav_lay.addSpacing(10)
        nav_lay.addWidget(btn_help)
        nav_lay.addWidget(btn_open)
        nav_lay.addWidget(self.btn_editor)
        nav_lay.addWidget(self.btn_export)
        main_lay.addWidget(self.nav)

        split = QSplitter(Qt.Horizontal)
        
        #/////////////////////////////////#
        #          SIDE PANELS            #
        #/////////////////////////////////#
        self.lp = QFrame()
        self.lp.setObjectName("SidePanel")
        lp_lay = QVBoxLayout(self.lp)
        
        header_lay = QHBoxLayout()
        self.chk_all = QCheckBox()
        self.chk_all.toggled.connect(self.toggle_all_files)
        lbl_assets = QLabel("PROJECT ASSETS")
        lbl_assets.setStyleSheet(f"color: {Config.COLOR_TEXT_MUTED}; font-weight: bold; font-size: 10px;")
        header_lay.addWidget(self.chk_all)
        header_lay.addWidget(lbl_assets)
        header_lay.addStretch()

        self.file_list = FileListWidget()
        self.file_list.itemClicked.connect(self.on_file_clicked)
        self.btn_batch = QPushButton("RUN BATCH PROCESS")
        self.btn_batch.setObjectName("ActionBtn")
        self.btn_batch.clicked.connect(self.on_start_batch)
        
        lp_lay.addLayout(header_lay)
        lp_lay.addWidget(self.file_list)
        lp_lay.addWidget(self.btn_batch)

        self.canvas = MangaCanvas()
        self.canvas.mask_changed.connect(lambda: self.history.push_mask_state(self.canvas.mask))
        self.canvas.mask_changed.connect(self.mark_current_modified)
        
        self.rp = QFrame()
        self.rp.setObjectName("SidePanel")
        rp_lay = QVBoxLayout(self.rp)
        
        self.mode_lbl = QLabel("MODE: PAINTING")
        self.mode_lbl.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-weight: bold; font-size: 10px;")
        rp_lay.addWidget(self.mode_lbl)
        
        self.tools = ToolGroup("Drawing Tools", ["MOVE", "BRUSH", "ERASER", "RECT", "LASSO", "POLY", "BUCKET", "CLEAR"])
        self.tools.buttons["MOVE"].clicked.connect(lambda: self.set_tool("NONE"))
        self.tools.buttons["BRUSH"].clicked.connect(lambda: self.set_tool("BRUSH"))
        self.tools.buttons["ERASER"].clicked.connect(lambda: self.set_tool("ERASER"))
        self.tools.buttons["RECT"].clicked.connect(lambda: self.set_tool("RECT"))
        self.tools.buttons["LASSO"].clicked.connect(lambda: self.set_tool("LASSO"))
        self.tools.buttons["POLY"].clicked.connect(lambda: self.set_tool("POLY"))
        self.tools.buttons["BUCKET"].clicked.connect(lambda: self.set_tool("BUCKET"))
        self.tools.buttons["CLEAR"].clicked.connect(self.canvas.clear_mask)
        
        self.b_slider = LabeledSlider("BRUSH SIZE", 40, 1, 300, self.canvas.set_brush_size)
        self.o_slider = LabeledSlider("MASK OPACITY", 60, 0, 100, self.canvas.set_mask_opacity, suffix="%")
        self.t_slider = LabeledSlider("MAX TILE SIZE", 2048, 512, 4096, is_tile=True)
        
        # Link dynamic canvas size updates to the sidebar slider UI
        self.canvas.brush_size_changed.connect(self.b_slider.slider.setValue)
        
        btn_scan = QPushButton("OCR SCAN [O]")
        btn_scan.setObjectName("ActionBtn")
        btn_scan.clicked.connect(self.on_ocr_scan)

        btn_trans = QPushButton("TRANSPARENCY SCAN [T]")
        btn_trans.setObjectName("ActionBtn")
        btn_trans.clicked.connect(self.on_transparency_scan)
        
        self.btn_clean = QPushButton("EXECUTE CLEAN [C]")
        self.btn_clean.setObjectName("PrimaryBtn")
        self.btn_clean.setFixedHeight(45)
        self.btn_clean.clicked.connect(self.on_lama_clean)
        
        self.queue_lbl = QLabel("Processing / Queued: 0")
        self.queue_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px;")
        self.queue_lbl.setAlignment(Qt.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(10)
        
        rp_lay.addWidget(self.tools)
        rp_lay.addWidget(self.b_slider)
        rp_lay.addWidget(self.o_slider)
        rp_lay.addSpacing(20)
        rp_lay.addWidget(btn_scan)
        rp_lay.addWidget(btn_trans)
        rp_lay.addWidget(self.t_slider)
        rp_lay.addWidget(self.btn_clean)
        rp_lay.addWidget(self.queue_lbl)
        rp_lay.addStretch()
        rp_lay.addWidget(self.progress_bar)
        
        split.addWidget(self.lp)
        split.addWidget(self.canvas)
        split.addWidget(self.rp)
        split.setSizes([220, 1000, 240])
        main_lay.addWidget(split, 1)

        # Enable OS File Drag & Drop
        self.setAcceptDrops(True)

        # Toast Notification Overlay
        self.toast = ToastNotification(self)

        #/////////////////////////////////#
        #          STATUS BAR             #
        #/////////////////////////////////#
        self.status_bar = self.statusBar()
        self.status_bar.setFixedHeight(26)

        self.status_tool_lbl = QLabel("Tool: Move")
        self.status_tool_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT_MUTED}; padding: 0 8px;")

        self.status_coord_lbl = QLabel("X: -  Y: -")
        self.status_coord_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT_MUTED}; padding: 0 8px;")

        self.status_dim_lbl = QLabel("")
        self.status_dim_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT_MUTED}; padding: 0 8px;")

        self.status_zoom_btn = QPushButton("100%")
        self.status_zoom_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {Config.COLOR_TEXT_MUTED};
                padding: 0 8px;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                color: {Config.COLOR_TEXT_PRIMARY};
            }}
        """)
        zoom_menu = QMenu(self)
        zoom_menu.addAction("Fit to Screen (Ctrl+0)").triggered.connect(self.canvas.fit_to_screen)
        zoom_menu.addAction("100% Actual Size (Ctrl+1)").triggered.connect(self.canvas.reset_zoom)
        zoom_menu.addAction("50%").triggered.connect(lambda: (self.canvas.reset_zoom(), self.canvas.zoom_by(0.5)))
        zoom_menu.addAction("200%").triggered.connect(lambda: (self.canvas.reset_zoom(), self.canvas.zoom_by(2.0)))
        self.status_zoom_btn.setMenu(zoom_menu)

        self.status_bar.addWidget(self.status_tool_lbl)
        self.status_bar.addPermanentWidget(self.status_coord_lbl)
        self.status_bar.addPermanentWidget(self.status_dim_lbl)
        self.status_bar.addPermanentWidget(self.status_zoom_btn)

        # Connect canvas signals to status bar telemetry
        self.canvas.mouse_moved.connect(lambda x, y: self.status_coord_lbl.setText(f"X: {x}  Y: {y}"))
        self.canvas.zoom_changed.connect(lambda z: self.status_zoom_btn.setText(f"{z}%"))

    def setup_shortcuts(self):
        QShortcut(QKeySequence("B"), self).activated.connect(lambda: self.set_tool("BRUSH"))
        QShortcut(QKeySequence("E"), self).activated.connect(lambda: self.set_tool("ERASER"))
        QShortcut(QKeySequence("R"), self).activated.connect(lambda: self.set_tool("RECT"))
        QShortcut(QKeySequence("L"), self).activated.connect(lambda: self.set_tool("LASSO"))
        QShortcut(QKeySequence("P"), self).activated.connect(lambda: self.set_tool("POLY"))
        QShortcut(QKeySequence("G"), self).activated.connect(lambda: self.set_tool("BUCKET"))
        QShortcut(QKeySequence("M"), self).activated.connect(lambda: self.set_tool("NONE"))
        
        QShortcut(QKeySequence("O"), self).activated.connect(self.on_ocr_scan)
        QShortcut(QKeySequence("T"), self).activated.connect(self.on_transparency_scan)
        QShortcut(QKeySequence("C"), self).activated.connect(self.on_lama_clean)
        
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.on_undo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self).activated.connect(self.on_redo)
        QShortcut(QKeySequence("Ctrl+Y"), self).activated.connect(self.on_redo)
        QShortcut(QKeySequence("Alt+Z"), self).activated.connect(self.on_undo)
        QShortcut(QKeySequence("Alt+Shift+Z"), self).activated.connect(self.on_redo)

        # Dynamic Brush Resize Brackets
        QShortcut(QKeySequence("["), self).activated.connect(lambda: self.adjust_brush_size(-5))
        QShortcut(QKeySequence("]"), self).activated.connect(lambda: self.adjust_brush_size(5))
        QShortcut(QKeySequence("Shift+["), self).activated.connect(lambda: self.adjust_brush_size(-20))
        QShortcut(QKeySequence("Shift+]"), self).activated.connect(lambda: self.adjust_brush_size(20))

        # Viewport Navigation & Zoom Presets
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self.canvas.fit_to_screen)
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(self.canvas.reset_zoom)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(lambda: self.canvas.zoom_by(1.25))
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(lambda: self.canvas.zoom_by(1.25))
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(lambda: self.canvas.zoom_by(0.8))
        QShortcut(QKeySequence("H"), self).activated.connect(self.canvas.toggle_flip_horizontal)

        # Mask Refinement & Selection Operations
        QShortcut(QKeySequence("Shift+>"), self).activated.connect(lambda: self.canvas.dilate_mask(3))
        QShortcut(QKeySequence("Shift+."), self).activated.connect(lambda: self.canvas.dilate_mask(3))
        QShortcut(QKeySequence("Shift+<"), self).activated.connect(lambda: self.canvas.erode_mask(3))
        QShortcut(QKeySequence("Shift+,"), self).activated.connect(lambda: self.canvas.erode_mask(3))
        QShortcut(QKeySequence("Ctrl+Shift+I"), self).activated.connect(self.canvas.invert_mask)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self.canvas.clear_mask)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.canvas.clear_mask)
        QShortcut(QKeySequence("Q"), self).activated.connect(self.canvas.toggle_quick_mask)
        QShortcut(QKeySequence("Ctrl+M"), self).activated.connect(self.canvas.cycle_mask_color)

        # Rapid Page Navigation
        QShortcut(QKeySequence("Page_Down"), self).activated.connect(lambda: self.navigate_file(1))
        QShortcut(QKeySequence("Page_Up"), self).activated.connect(lambda: self.navigate_file(-1))
        QShortcut(QKeySequence("Ctrl+Right"), self).activated.connect(lambda: self.navigate_file(1))
        QShortcut(QKeySequence("Ctrl+Left"), self).activated.connect(lambda: self.navigate_file(-1))
        QShortcut(QKeySequence("Alt+Right"), self).activated.connect(lambda: self.navigate_file(1))
        QShortcut(QKeySequence("Alt+Left"), self).activated.connect(lambda: self.navigate_file(-1))

        # Quick Save & Export
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.on_quick_save)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self).activated.connect(lambda: self.on_export("png"))

    def adjust_brush_size(self, delta):
        new_size = max(1, min(300, self.canvas.brush_size + delta))
        self.canvas.set_brush_size(new_size, show_hud=True)

    def keyPressEvent(self, event):
        # Trigger inverse tool temporarily if Alt is held down
        if event.key() == Qt.Key_Alt and not event.isAutoRepeat():
            if self.canvas.current_tool == "BRUSH":
                self.is_alt_erasing = True
                self.set_tool("ERASER")
            elif self.canvas.current_tool == "ERASER":
                self.is_alt_brushing = True
                self.set_tool("BRUSH")
                
        # Trigger Move temporarily if Space is held down
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if not getattr(self, 'is_space_moving', False):
                self.is_space_moving = True
                self.pre_space_tool = self.canvas.current_tool
                self.set_tool("NONE")

        # Hold Backslash to Compare with Original Scan
        if event.key() == Qt.Key_Backslash and not event.isAutoRepeat():
            self.canvas.show_comparison(True)
                
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        # Release Backslash to return to cleaned/current view
        if event.key() == Qt.Key_Backslash and not event.isAutoRepeat():
            self.canvas.show_comparison(False)

        # Snap back to opposite tool when Alt is released
        if event.key() == Qt.Key_Alt and not event.isAutoRepeat():
            if getattr(self, 'is_alt_erasing', False):
                self.is_alt_erasing = False
                if self.canvas.current_tool == "ERASER":
                    self.set_tool("BRUSH")
            elif getattr(self, 'is_alt_brushing', False):
                self.is_alt_brushing = False
                if self.canvas.current_tool == "BRUSH":
                    self.set_tool("ERASER")
                    
        # Snap back to previous tool when Space is released
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if getattr(self, 'is_space_moving', False):
                self.is_space_moving = False
                if self.canvas.current_tool == "NONE":
                    self.set_tool(self.pre_space_tool)
                    
        super().keyReleaseEvent(event)

    def set_tool(self, tool):
        # Prevent dangling poly lines if user swaps tools mid-selection
        if self.canvas.current_tool == "POLY" and tool != "POLY":
            self.canvas.poly_points.clear()
            self.canvas.preview_item.setPath(QPainterPath())

        self.canvas.current_tool = tool
        for btn in self.tools.buttons.values(): 
            btn.setChecked(False)
        
        # Ensure correct visual cursor state
        self.canvas.update_cursor_visuals()
        
        if tool == "NONE":
            self.canvas.setDragMode(QGraphicsView.ScrollHandDrag)
            self.canvas.viewport().unsetCursor()
            self.canvas.cursor_item.hide()
            self.tools.buttons["MOVE"].setChecked(True)
            self.mode_lbl.setText("MODE: MOVING")
            self.mode_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT_MUTED}; font-weight: bold;")
            
        else:
            self.canvas.setDragMode(QGraphicsView.NoDrag)
            
            if tool in ["BRUSH", "ERASER"]:
                if not self.canvas.is_locked:
                    self.canvas.viewport().setCursor(Qt.BlankCursor)
                    self.canvas.cursor_item.show()
                else:
                    self.canvas.viewport().unsetCursor()
            else:
                if not self.canvas.is_locked:
                    self.canvas.viewport().setCursor(Qt.CrossCursor)
                else:
                    self.canvas.viewport().unsetCursor()
                self.canvas.cursor_item.hide()
            
            mapping = {"BRUSH": "BRUSH", "ERASER": "ERASER", "RECT": "RECT", "LASSO": "LASSO", "POLY": "POLY", "BUCKET": "BUCKET"}
            if tool in mapping: 
                self.tools.buttons[mapping[tool]].setChecked(True)
            
            if tool == "ERASER":
                self.mode_lbl.setText("MODE: ERASING")
                self.mode_lbl.setStyleSheet(f"color: {Config.COLOR_MODIFIED}; font-weight: bold;")
            elif tool == "BUCKET":
                self.mode_lbl.setText("MODE: FILLING")
                self.mode_lbl.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-weight: bold;")
            else:
                self.mode_lbl.setText("MODE: PAINTING")
                self.mode_lbl.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-weight: bold;")

        tool_names = {
            "NONE": "Move",
            "BRUSH": "Brush",
            "ERASER": "Eraser",
            "RECT": "Rectangle",
            "LASSO": "Lasso",
            "POLY": "Polygonal",
            "BUCKET": "Bucket Fill"
        }
        if hasattr(self, 'status_tool_lbl'):
            self.status_tool_lbl.setText(f"Tool: {tool_names.get(tool, tool.capitalize())}")

    def toggle_all_files(self, checked):
        """Checks or unchecks all files in the list"""
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(state)

    #/////////////////////////////////#
    #      HISTORY OPERATIONS         #
    #/////////////////////////////////#

    def on_undo(self):
        if self.canvas.is_locked: return
        res = self.history.undo(self.canvas.cv_img, self.canvas.mask)
        if not res: return

        self.mark_current_modified()
        if res.get("type") == "mask":
            self.canvas.mask = res["mask"].copy()
            self.canvas.update_mask_display()
        elif res.get("type") == "image":
            self.canvas.set_image(res["img"])
            if res.get("restore_mask") is not None:
                self.canvas.mask = res["restore_mask"].copy()
                self.canvas.update_mask_display()

    def on_redo(self):
        if self.canvas.is_locked: return
        res = self.history.redo(self.canvas.cv_img, self.canvas.mask)
        if not res: return

        self.mark_current_modified()
        if res.get("type") == "mask":
            self.canvas.mask = res["mask"].copy()
            self.canvas.update_mask_display()
        elif res.get("type") == "image":
            self.canvas.set_image(res["img"])
            if res.get("clear_mask"):
                self.canvas.clear_mask()

    def on_undo_image(self):
        self.on_undo()

    def on_redo_image(self):
        self.on_redo()

    def on_undo_mask(self):
        self.on_undo()

    def on_redo_mask(self):
        self.on_redo()

    #/////////////////////////////////#
    #      AI EXECUTION PIPELINE      #
    #/////////////////////////////////#

    def _check_lock_state(self):
        """Identifies ALL files currently being processed or waiting and globally updates UI"""
        locked_paths = set()
        
        # 1. Grab file currently running in AI worker thread
        if self.worker_thread is not None and hasattr(self, 'worker'):
            active_path = getattr(self.worker, 'source_path', None)
            if active_path: locked_paths.add(active_path)
            
        # 2. Grab all manual/single-task queued files
        for item in self.task_queue:
            locked_paths.add(item["path"])
                
        # 3. Grab all remaining files waiting in the Batch Engine queue
        if self.is_batching:
            for idx in range(self.batch_engine.current_index, len(self.batch_engine.files)):
                locked_paths.add(self.batch_engine.files[idx])

        # 4. Globally update the FileList UI checkboxes and lock icons
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            file_path = item.data(Qt.UserRole)
            is_locked = (file_path in locked_paths)
            item.setData(Qt.UserRole + 2, is_locked)

        # 5. Lock/Unlock the main interactive Canvas if we're looking at a locked file
        if self.current_img_path:
            self.canvas.set_locked(self.current_img_path in locked_paths)
        else:
            self.canvas.set_locked(False)

    def _update_queue_ui(self):
        """Updates the status label, global progress bar, and active lock states"""
        pending = self.total_lama_tasks - self.completed_lama_tasks
        self.queue_lbl.setText(f"Processing / Queued: {pending}")

        if pending > 0 and self.total_lama_tasks > 0:
            val = int((self.completed_lama_tasks / self.total_lama_tasks) * 100)
            self.progress_bar.setValue(val)
            self.progress_bar.setVisible(True)
        else:
            self.progress_bar.setVisible(False)
            self.total_lama_tasks = 0
            self.completed_lama_tasks = 0
            
        self._check_lock_state()

    def on_worker_progress(self, val):
        """Calculates fractional progress for smooth overall queue tracking"""
        if self.worker.task != "clean" or self.total_lama_tasks == 0: return
        base_progress = (self.completed_lama_tasks / self.total_lama_tasks) * 100
        task_fraction = (val / 100.0) * (100 / self.total_lama_tasks)
        self.progress_bar.setValue(int(base_progress + task_fraction))

    def enqueue_task(self, task, path, *args):
        """Pushes an AI task into the FIFO queue and triggers the processor"""
        self.task_queue.append({
            "task": task,
            "path": path,
            "args": args
        })
        self._update_queue_ui()
        self._process_queue()

    def _process_queue(self):
        """Pulls the next task from the queue and runs it"""
        if self.worker_thread is not None:
            return

        if not self.task_queue:
            self._update_queue_ui()
            # Models stay resident in VRAM for instant subsequent inferences
            return

        item = self.task_queue.pop(0)
        source_path = item["path"]
        
        # Update status to WAITING since AI is processing it now
        self.page_states[source_path] = PageState.WAITING
        self.file_list.update_item_state(source_path, "waiting")

        self.setCursor(Qt.WaitCursor)
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
        self.setCursor(Qt.ArrowCursor)
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None
        self._update_queue_ui()

    def on_task_error(self, message):
        source_path = getattr(self.worker, 'source_path', None)
        if source_path:
            self.page_states[source_path] = PageState.ERROR
            self.file_list.update_item_state(source_path, "error")

        self.stop_thread()
        self.is_batching = False
        self.task_queue.clear()
        self.total_lama_tasks = 0
        self.completed_lama_tasks = 0
        self._update_queue_ui()
        QMessageBox.critical(self, "Hardware Error", message)

    def on_task_finished(self, result, patches):
        task = self.worker.task  
        source_path = getattr(self.worker, 'source_path', self.current_img_path)
        is_active = (source_path == self.current_img_path)

        new_state = PageState.READY if task == "clean" else PageState.MODIFIED
        self.page_states[source_path] = new_state
        self.file_list.update_item_state(source_path, new_state.name.lower())

        if task == "clean":
            self.completed_lama_tasks += 1
            target_history = self.history if is_active else self.image_sessions[source_path]["history"]
            saved_mask = self.canvas.mask.copy() if is_active else self.image_sessions[source_path]["mask"].copy()
            if len(patches) > 0:
                target_history.push_image_clean(patches, result, saved_mask=saved_mask)

            if is_active:
                self.canvas.set_image(result)
                self.canvas.clear_mask()
            else:
                self.image_sessions[source_path]["img"] = result
                self.image_sessions[source_path]["mask"].fill(Qt.transparent)

        elif task in ["ocr", "transparency"]:
            target_history = self.history if is_active else self.image_sessions[source_path]["history"]
            current_mask = self.canvas.mask if is_active else self.image_sessions[source_path]["mask"]
            target_history.push_mask_state(current_mask)

            h, w = result.shape[:2]
            rgba = np.zeros((h, w, 4), dtype=np.uint8)
            rgba[result > 0] = [0, 255, 0, 255] if task == "transparency" else [244, 63, 94, 255]
            new_mask = QImage(rgba.data, w, h, w*4, QImage.Format_ARGB32).copy()

            if is_active:
                self.canvas.mask = new_mask
                self.canvas.update_mask_display()
            else:
                self.image_sessions[source_path]["mask"] = new_mask

        self.stop_thread()

        # Handle Background Batching Loop
        if self.is_batching:
            if task == "clean":
                final_img = self.canvas.cv_img if is_active else self.image_sessions[source_path]["img"]
                is_last = self.batch_engine.save_current(final_img)
                if is_last: self.finalize_batch()
                else: self.step_batch()
            elif task in ["ocr", "transparency"]:
                mask_q = self.canvas.mask if is_active else self.image_sessions[source_path]["mask"]
                img_cv = self.canvas.cv_img if is_active else self.image_sessions[source_path]["img"]

                ptr = mask_q.bits()
                mask_np = np.frombuffer(ptr, np.uint8).reshape((mask_q.height(), mask_q.width(), 4))
                mask_gray = mask_np[:, :, 3].copy()
                t_size = self.t_slider.slider.value() * 512
                self.enqueue_task("clean", source_path, img_cv.copy(), mask_gray, t_size)

        self._process_queue()

    def on_ocr_scan(self):
        if self.canvas.cv_img is None or self.canvas.is_locked: return
        self.mark_current_modified()
        self.enqueue_task("ocr", self.current_img_path, self.canvas.cv_img.copy())

    def on_transparency_scan(self):
        if self.canvas.cv_img is None or not self.current_img_path or self.canvas.is_locked: return
        self.mark_current_modified()
        self.enqueue_task("transparency", self.current_img_path, self.canvas.cv_img.copy())

    def on_lama_clean(self):
        if self.canvas.cv_img is None or self.canvas.is_locked: return
        ptr = self.canvas.mask.bits()
        mask_np = np.frombuffer(ptr, np.uint8).reshape((self.canvas.mask.height(), self.canvas.mask.width(), 4))
        mask_gray = mask_np[:, :, 3].copy()

        if not np.any(mask_gray):
            if self.is_batching:
                is_last = self.batch_engine.save_current(self.canvas.cv_img)
                if is_last: self.finalize_batch()
                else: self.step_batch()
            else:
                self.show_toast("No mask area detected", "warning")
            return

        self.total_lama_tasks += 1
        t_size = self.t_slider.slider.value() * 512
        self.mark_current_modified()
        self.enqueue_task("clean", self.current_img_path, self.canvas.cv_img.copy(), mask_gray, t_size)

    #/////////////////////////////////#
    #    BATCH & PHOTOSHOP BRIDGE     #
    #/////////////////////////////////#

    def on_start_batch(self):
        if self.file_list.count() == 0: return

        dialog = BatchSetupDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        scan_choice, fmt = dialog.get_results()
        if scan_choice == "Transparency Scan": self.batch_scan_type = "transparency"
        elif scan_choice == "Mask": self.batch_scan_type = "mask"
        elif scan_choice == "none": self.batch_scan_type = "none"
        else: self.batch_scan_type = "ocr"

        # Check if any specific files were checked in the UI
        paths = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.Checked:
                paths.append(item.data(Qt.UserRole))

        # If absolutely no checkboxes are checked, default to ALL files
        if not paths:
            self.chk_all.setChecked(True)
            paths = [self.file_list.item(i).data(Qt.UserRole) for i in range(self.file_list.count())]

        self.batch_engine.initialize_batch(paths, fmt)
        self.is_batching = True
        self.total_lama_tasks += len(paths)
        self.step_batch()
        self._check_lock_state()

    def step_batch(self):
        path = self.batch_engine.get_next()
        if path:
            if path not in self.image_sessions:
                img_data = np.fromfile(path, dtype=np.uint8)
                img = cv2.imdecode(img_data, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    if len(img.shape) == 2: img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                    elif len(img.shape) == 3 and img.shape[2] == 4: img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                    else: img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                    self.image_sessions[path] = {
                        "img": img.copy(),
                        "orig": img.copy(),
                        "mask": QImage(img.shape[1], img.shape[0], QImage.Format_ARGB32),
                        "history": HistoryManager(Config.MAX_HISTORY)
                    }
                    self.image_sessions[path]["mask"].fill(Qt.transparent)

            is_active = (path == self.current_img_path)

            if self.batch_scan_type == "none":
                img_cv = self.canvas.cv_img if is_active else self.image_sessions[path]["img"]
                self.total_lama_tasks -= 1
                
                self.page_states[path] = PageState.READY
                self.file_list.update_item_state(path, "ready")
                self._update_queue_ui()
                
                is_last = self.batch_engine.save_current(img_cv)
                if is_last: self.finalize_batch()
                else: QTimer.singleShot(0, self.step_batch)
                return
                
            elif self.batch_scan_type == "mask":
                mask_q = self.canvas.mask if is_active else self.image_sessions[path]["mask"]
                img_cv = self.canvas.cv_img if is_active else self.image_sessions[path]["img"]

                ptr = mask_q.bits()
                mask_np = np.frombuffer(ptr, np.uint8).reshape((mask_q.height(), mask_q.width(), 4))
                mask_gray = mask_np[:, :, 3].copy()

                if not np.any(mask_gray):
                    self.total_lama_tasks -= 1
                    self.page_states[path] = PageState.READY
                    self.file_list.update_item_state(path, "ready")
                    self._update_queue_ui()
                    
                    is_last = self.batch_engine.save_current(img_cv)
                    if is_last: self.finalize_batch()
                    else: QTimer.singleShot(0, self.step_batch)
                    return

                t_size = self.t_slider.slider.value() * 512
                self.enqueue_task("clean", path, img_cv.copy(), mask_gray, t_size)
            else:
                img_cv = self.canvas.cv_img if is_active else self.image_sessions[path]["img"]
                self.enqueue_task(self.batch_scan_type, path, img_cv.copy())

    def finalize_batch(self):
        self.is_batching = False
        self._check_lock_state()
        
        self.setCursor(Qt.WaitCursor)
        if self.batch_engine.export_format == "photoshop":
            PhotoshopBridge.open_batch_in_ps(self.batch_engine.files, self.batch_engine.output_dir)
        elif self.batch_engine.export_format == "photopea":
            PhotopeaBridge.open_batch_in_photopea(self.batch_engine.files, self.batch_engine.output_dir)
        self.setCursor(Qt.ArrowCursor)
            
        if self.batch_engine.export_format == "none":
            self.show_toast("Batch Complete: Pages updated in studio memory", "success", 4000)
        else:
            self.show_toast(f"Batch Complete: Saved to {os.path.basename(self.batch_engine.output_dir)}", "success", 4000)

    #/////////////////////////////////#
    #        FILE OPERATIONS          #
    #/////////////////////////////////#

    def on_open_folder(self):
        p = QFileDialog.getExistingDirectory(self, "Select Folder")
        if p:
            self.load_folder(p)

    def load_folder(self, folder_path: str):
        if not os.path.isdir(folder_path):
            return
        valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
        files = [os.path.join(folder_path, f) for f in sorted(os.listdir(folder_path)) if f.lower().endswith(valid_exts)]
        if files:
            self.load_files(files)
            self.show_toast(f"Loaded {len(files)} pages", "info")
        else:
            self.show_toast("No supported images found in folder", "warning")

    def load_files(self, file_paths: list):
        self.image_sessions.clear()
        self.page_states.clear()
        self.file_list.clear()
        for full_path in file_paths:
            self.page_states[full_path] = PageState.UNMODIFIED
            self.file_list.add_file(full_path)
        if self.file_list.count() > 0:
            self.file_list.setCurrentRow(0)
            item = self.file_list.item(0)
            if item:
                self.on_file_clicked(item)

    def navigate_file(self, direction: int):
        total = self.file_list.count()
        if total == 0:
            return
        curr = self.file_list.currentRow()
        if curr < 0:
            next_idx = 0 if direction > 0 else total - 1
        else:
            next_idx = (curr + direction) % total
        self.file_list.setCurrentRow(next_idx)
        item = self.file_list.item(next_idx)
        if item:
            self.on_file_clicked(item)

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
        if not event.mimeData().hasUrls():
            return
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if not paths:
            return

        valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
        files_to_load = []

        if len(paths) == 1 and os.path.isdir(paths[0]):
            self.load_folder(paths[0])
            event.acceptProposedAction()
            return

        for p in paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in sorted(files):
                        if f.lower().endswith(valid_exts):
                            files_to_load.append(os.path.join(root, f))
            elif p.lower().endswith(valid_exts):
                files_to_load.append(p)

        if files_to_load:
            self.load_files(files_to_load)
            self.show_toast(f"Loaded {len(files_to_load)} dragged files", "info")
            event.acceptProposedAction()

    def show_toast(self, message: str, level: str = "info", duration: int = 3000):
        if hasattr(self, 'toast'):
            self.toast.show_toast(message, level, duration)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'toast') and self.toast.isVisible():
            x = self.width() - self.toast.width() - 24
            y = self.height() - self.toast.height() - 36
            self.toast.move(x, y)

    def on_quick_save(self):
        if self.canvas.cv_img is None or not self.current_img_path:
            self.show_toast("No active image to save", "warning")
            return

        os.makedirs(Paths.PROCESSED, exist_ok=True)
        filename = os.path.basename(self.current_img_path)
        out_path = os.path.join(Paths.PROCESSED, filename)

        img = self.canvas.cv_img
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
            self.file_list.update_item_state(self.current_img_path, "ready")
            self.show_toast(f"Quick-saved: {filename}", "success")
        else:
            self.show_toast("Failed to encode image", "error")

    def mark_current_modified(self):
        """Transitions the page state to MODIFIED via Enum"""
        if self.current_img_path:
            if self.page_states.get(self.current_img_path) != PageState.MODIFIED:
                self.page_states[self.current_img_path] = PageState.MODIFIED
                self.file_list.update_item_state(self.current_img_path, "modified")

    def on_file_clicked(self, it):
        path_real = it.data(Qt.UserRole)
        if path_real == self.current_img_path: return 

        if self.current_img_path and self.canvas.cv_img is not None:
            self.image_sessions[self.current_img_path] = {
                "img": self.canvas.cv_img.copy(),
                "orig": getattr(self.canvas, 'orig_img', self.canvas.cv_img).copy(),
                "mask": self.canvas.mask.copy(),
                "history": self.history
            }

        self.current_img_path = path_real

        if path_real in self.image_sessions:
            session = self.image_sessions[path_real]
            self.history = session["history"]
            self.canvas.set_image(session["img"], orig_img=session.get("orig"))
            self.canvas.mask = session["mask"].copy()
            self.canvas.update_mask_display()
        else:
            img_data = np.fromfile(path_real, dtype=np.uint8)
            img = cv2.imdecode(img_data, cv2.IMREAD_UNCHANGED)

            if img is not None:
                if len(img.shape) == 2: img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                elif len(img.shape) == 3 and img.shape[2] == 4: img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                else: img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                self.history = HistoryManager(Config.MAX_HISTORY)
                self.canvas.set_image(img, orig_img=img)
                
                self.image_sessions[path_real] = {
                    "img": img.copy(),
                    "orig": img.copy(),
                    "mask": self.canvas.mask.copy(),
                    "history": self.history
                }
            else:
                self.show_toast(f"Corrupted or invalid image: {os.path.basename(path_real)}", "error")
                logger.error(f"Failed to decode image: {path_real}")
                
        # Update status bar dimensions & color mode
        if hasattr(self, 'status_dim_lbl') and self.canvas.cv_img is not None:
            h, w = self.canvas.cv_img.shape[:2]
            channels = "RGBA" if (len(self.canvas.cv_img.shape) == 3 and self.canvas.cv_img.shape[2] == 4) else "RGB"
            self.status_dim_lbl.setText(f"{w} × {h} px · {channels}")

        self._check_lock_state()

    def on_export(self, fmt):
        if self.canvas.cv_img is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Export", "", f"{fmt.upper()} (*.{fmt})")
        if path:
            if len(self.canvas.cv_img.shape) == 3 and self.canvas.cv_img.shape[2] == 4:
                img_out = cv2.cvtColor(self.canvas.cv_img, cv2.COLOR_RGBA2BGRA)
                if fmt.lower() in ["jpg", "jpeg"]:
                    img_out = cv2.cvtColor(img_out, cv2.COLOR_BGRA2BGR)
            else:
                img_out = cv2.cvtColor(self.canvas.cv_img, cv2.COLOR_RGB2BGR)
                
            ext = os.path.splitext(path)[1]
            is_success, im_buf_arr = cv2.imencode(ext, img_out)
            if is_success:
                im_buf_arr.tofile(path)
                self.show_toast(f"Exported: {os.path.basename(path)}", "success")

    def on_editor_bridge(self, target="photoshop"):
        if self.canvas.cv_img is None or not self.current_img_path: return

        img_data = np.fromfile(self.current_img_path, dtype=np.uint8)
        orig = cv2.imdecode(img_data, cv2.IMREAD_UNCHANGED)

        if orig is not None:
            if len(orig.shape) == 3 and orig.shape[2] == 4:
                orig = cv2.cvtColor(orig, cv2.COLOR_BGRA2RGBA)
            else:
                orig = cv2.cvtColor(orig, cv2.COLOR_BGR2RGB)

            self.setCursor(Qt.WaitCursor)
            if target == "photoshop":
                res = PhotoshopBridge.send_to_ps(orig, self.canvas.cv_img)
            elif target == "photopea":
                res = PhotopeaBridge.send_to_photopea(orig, self.canvas.cv_img, self.current_img_path)
            self.setCursor(Qt.ArrowCursor)

            if res != "Success":
                logger.error(f"[X] UI Blocked Editor Bridge Transfer: {res}")
                QMessageBox.warning(self, "Editor Error", f"Could not send to {target.capitalize()}:\n{res}\n\nCheck your logs folder for details.")

    def update_telemetry(self):
        ram, gpu = self.monitor.get_stats()
        self.hw_mon.lbl.setText(f"{'GPU' if gpu else 'CPU'} | RAM: {ram}MB")
        self.hw_mon.bar.setValue(min(ram // 40, 100))

#/////////////////////////////////#
#    BATCH SETUP DIALOG MODAL     #
#/////////////////////////////////#

class BatchSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Setup")
        self.setStyleSheet(f"background-color: {Config.COLOR_PANEL}; color: {Config.COLOR_TEXT};")

        self.scan_mode = QComboBox()
        self.scan_mode.addItems(["none", "Mask", "OCR Scan", "Transparency Scan"])
        self.scan_mode.setStyleSheet(f"background-color: {Config.COLOR_BG}; border: 1px solid {Config.COLOR_BORDER_SUBTLE}; padding: 4px;")

        self.export_fmt = QComboBox()
        self.export_fmt.addItems(["none", "png", "jpg", "photoshop", "photopea"])
        self.export_fmt.setStyleSheet(f"background-color: {Config.COLOR_BG}; border: 1px solid {Config.COLOR_BORDER_SUBTLE}; padding: 4px;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.setStyleSheet(f"QPushButton {{ background-color: {Config.COLOR_BG}; border: 1px solid {Config.COLOR_BORDER_SUBTLE}; padding: 6px; }}")

        layout = QFormLayout(self)
        layout.addRow("Scan Mode:", self.scan_mode)
        layout.addRow("Export Format:", self.export_fmt)
        layout.addWidget(buttons)

    def get_results(self):
        return self.scan_mode.currentText(), self.export_fmt.currentText()