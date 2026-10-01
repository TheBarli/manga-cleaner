import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QSplitter,
                             QMenu, QProgressBar, QCheckBox, QMessageBox)
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import Qt, QTimer
from src.frontend.widgets import FileListWidget, ToolGroup, LabeledSlider, HardwareMonitor, ToastNotification
from src.frontend.canvas import MangaCanvas
from src.frontend.help_system import HelpSystem
from src.frontend.dialogs.batch_setup import BatchSetupDialog
from src.frontend.controllers import (
    ToolController, SessionManager, PageState, PipelineController, BatchController
)
from src.utils.system_info import SystemMonitor
from src.utils.history import HistoryManager
from src.utils.config import Config
from src.utils.logger import logger
from src.utils.preferences import UserPrefs


#/////////////////////////////////#
#   STUDIO MAIN CONTROLLER        #
#/////////////////////////////////#

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{Config.APP_NAME} v{Config.VERSION}")
        self.resize(1500, 900)

        self.monitor = SystemMonitor()
        self.history = HistoryManager(Config.MAX_HISTORY, on_change=self.update_history_ui)

        # Domain Controllers
        self.session_manager = SessionManager(self)
        self.batch_controller = BatchController(self)
        self.pipeline_controller = PipelineController(self)
        self.tool_controller = ToolController(self)

        self.init_ui()
        self.setup_shortcuts()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_telemetry)
        self.timer.start(2000)
        logger.info("--- STUDIO INTERFACE READY ---")

    #/////////////////////////////////#
    #    BACKWARD COMPATIBILITY       #
    #/////////////////////////////////#

    @property
    def image_sessions(self):
        return self.session_manager.image_sessions

    @property
    def page_states(self):
        return self.session_manager.page_states

    @property
    def current_img_path(self):
        return self.session_manager.current_img_path

    @current_img_path.setter
    def current_img_path(self, val):
        self.session_manager.current_img_path = val

    @property
    def max_cached_sessions(self):
        return self.session_manager.max_cached_sessions

    @max_cached_sessions.setter
    def max_cached_sessions(self, val):
        self.session_manager.set_max_cached_sessions(val)

    @property
    def batch_engine(self):
        return self.batch_controller.batch_engine

    @property
    def is_batching(self):
        return self.batch_controller.is_batching

    @is_batching.setter
    def is_batching(self, val):
        self.batch_controller.is_batching = val

    @property
    def batch_scan_type(self):
        return self.batch_controller.batch_scan_type

    @batch_scan_type.setter
    def batch_scan_type(self, val):
        self.batch_controller.batch_scan_type = val

    @property
    def task_queue(self):
        return self.pipeline_controller.task_queue

    @property
    def total_tasks(self):
        return self.pipeline_controller.total_tasks

    @total_tasks.setter
    def total_tasks(self, val):
        self.pipeline_controller.total_tasks = val

    @property
    def completed_tasks(self):
        return self.pipeline_controller.completed_tasks

    @completed_tasks.setter
    def completed_tasks(self, val):
        self.pipeline_controller.completed_tasks = val

    @property
    def total_lama_tasks(self):
        return self.pipeline_controller.total_lama_tasks

    @total_lama_tasks.setter
    def total_lama_tasks(self, val):
        self.pipeline_controller.total_lama_tasks = val

    @property
    def completed_lama_tasks(self):
        return self.pipeline_controller.completed_lama_tasks

    @completed_lama_tasks.setter
    def completed_lama_tasks(self, val):
        self.pipeline_controller.completed_lama_tasks = val

    @property
    def worker_thread(self):
        return self.pipeline_controller.worker_thread

    @worker_thread.setter
    def worker_thread(self, val):
        self.pipeline_controller.worker_thread = val

    @property
    def worker(self):
        return self.pipeline_controller.worker

    @worker.setter
    def worker(self, val):
        self.pipeline_controller.worker = val

    @property
    def is_alt_erasing(self):
        return self.tool_controller.is_alt_erasing

    @is_alt_erasing.setter
    def is_alt_erasing(self, val):
        self.tool_controller.is_alt_erasing = val

    @property
    def is_alt_brushing(self):
        return self.tool_controller.is_alt_brushing

    @is_alt_brushing.setter
    def is_alt_brushing(self, val):
        self.tool_controller.is_alt_brushing = val

    @property
    def is_space_moving(self):
        return self.tool_controller.is_space_moving

    @is_space_moving.setter
    def is_space_moving(self, val):
        self.tool_controller.is_space_moving = val

    @property
    def pre_space_tool(self):
        return self.tool_controller.pre_space_tool

    @pre_space_tool.setter
    def pre_space_tool(self, val):
        self.tool_controller.pre_space_tool = val

    #/////////////////////////////////#
    #         UI CONSTRUCTION         #
    #/////////////////////////////////#

    def init_ui(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        main_lay = QVBoxLayout(self.central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # Hardware Monitor telemetry widget (hosted in bottom status bar)
        self.hw_mon = HardwareMonitor()

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
        self.btn_batch.setToolTip("Run Batch Clean")
        self.btn_batch.clicked.connect(self.on_start_batch)
        
        lp_lay.addLayout(header_lay)
        lp_lay.addWidget(self.file_list)
        lp_lay.addWidget(self.btn_batch)

        self.canvas = MangaCanvas()
        self.canvas.mask_changed.connect(lambda: self.history.push_mask_state(self.canvas.mask))
        self.canvas.mask_changed.connect(self.mark_current_modified)
        self.canvas.open_image_requested.connect(self.on_open_image)
        self.canvas.open_folder_requested.connect(self.on_open_folder)
        
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

        # Minimalist Single-Line Tooltips (Pro Standard)
        self.tools.buttons["MOVE"].setToolTip("Move / Pan Canvas (M / Space)")
        self.tools.buttons["BRUSH"].setToolTip("Brush Tool (B)")
        self.tools.buttons["ERASER"].setToolTip("Eraser Tool (E)")
        self.tools.buttons["RECT"].setToolTip("Rectangle Selection (R)")
        self.tools.buttons["LASSO"].setToolTip("Lasso Selection (L)")
        self.tools.buttons["POLY"].setToolTip("Polygonal Selection (P)")
        self.tools.buttons["BUCKET"].setToolTip("Bucket Fill (G)")
        self.tools.buttons["CLEAR"].setToolTip("Clear Mask (Ctrl+D / Esc)")
        
        # Load saved slider preferences
        saved_brush = UserPrefs.load("brush_size", 40, type=int)
        saved_opacity = UserPrefs.load("mask_opacity", 60, type=int)
        saved_tile = UserPrefs.load("tile_size", 2048, type=int)

        self.b_slider = LabeledSlider("BRUSH SIZE", saved_brush, 1, 300, self.canvas.set_brush_size)
        self.b_slider.setToolTip("Brush Size (1-300px) [ / ]")
        self.o_slider = LabeledSlider("MASK OPACITY", saved_opacity, 0, 100, self.canvas.set_mask_opacity, suffix="%")
        self.o_slider.setToolTip("Mask Opacity (10-100%)")
        self.t_slider = LabeledSlider("MAX TILE SIZE", saved_tile, 512, 4096, is_tile=True)
        self.t_slider.setToolTip("Max Tile Size (512-4096px)")
        
        # Link dynamic canvas size updates to the sidebar slider UI
        self.canvas.brush_size_changed.connect(self.b_slider.slider.setValue)
        self.canvas.set_brush_size(saved_brush)
        self.canvas.set_mask_opacity(saved_opacity)

        # Hook slider changes to persist in UserPrefs
        self.b_slider.slider.valueChanged.connect(lambda v: UserPrefs.save("brush_size", v))
        self.o_slider.slider.valueChanged.connect(lambda v: UserPrefs.save("mask_opacity", v))
        self.t_slider.slider.valueChanged.connect(lambda v: UserPrefs.save("tile_size", v * 512))
        
        btn_scan = QPushButton("OCR SCAN [O]")
        btn_scan.setObjectName("ActionBtn")
        btn_scan.setToolTip("Auto-Detect Text (O)")
        btn_scan.clicked.connect(self.on_ocr_scan)

        btn_trans = QPushButton("TRANSPARENCY SCAN [T]")
        btn_trans.setObjectName("ActionBtn")
        btn_trans.setToolTip("Auto-Detect Transparency (T)")
        btn_trans.clicked.connect(self.on_transparency_scan)
        
        self.btn_clean = QPushButton("EXECUTE CLEAN [C]")
        self.btn_clean.setObjectName("PrimaryBtn")
        self.btn_clean.setFixedHeight(45)
        self.btn_clean.setToolTip("Execute Clean (C)")
        self.btn_clean.clicked.connect(self.on_lama_clean)

        self.btn_export = QPushButton("EXPORT")
        self.btn_export.setObjectName("ActionBtn")
        self.btn_export.setFixedHeight(34)
        self.btn_export.setToolTip("Export Image (Ctrl+Shift+S)")
        self.btn_export.clicked.connect(self.on_export)

        self.btn_photopea = QPushButton("SEND TO PHOTOPEA")
        self.btn_photopea.setObjectName("ActionBtn")
        self.btn_photopea.setFixedHeight(30)
        self.btn_photopea.setToolTip("Open Original + Cleaned as layers in Photopea (browser)")
        self.btn_photopea.clicked.connect(self.on_send_to_photopea)

        if os.name == 'nt':
            self.btn_photoshop = QPushButton("SEND TO PHOTOSHOP")
            self.btn_photoshop.setObjectName("ActionBtn")
            self.btn_photoshop.setFixedHeight(30)
            self.btn_photoshop.setToolTip("Open Original + Cleaned as layers in Adobe Photoshop")
            self.btn_photoshop.clicked.connect(self.on_send_to_photoshop)
        
        self.queue_lbl = QLabel("Processing / Queued: 0")
        self.queue_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT_DIM}; font-size: 10px;")
        self.queue_lbl.setAlignment(Qt.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(10)
        
        rp_lay.addWidget(self.tools)
        rp_lay.addWidget(self.b_slider)
        rp_lay.addWidget(self.o_slider)
        rp_lay.addSpacing(16)
        rp_lay.addWidget(btn_scan)
        rp_lay.addWidget(btn_trans)
        rp_lay.addWidget(self.t_slider)
        rp_lay.addWidget(self.btn_clean)
        rp_lay.addWidget(self.btn_export)
        rp_lay.addWidget(self.btn_photopea)
        if os.name == 'nt':
            rp_lay.addWidget(self.btn_photoshop)
        rp_lay.addWidget(self.queue_lbl)
        rp_lay.addStretch()
        rp_lay.addWidget(self.progress_bar)
        
        self.split = split
        self.split.addWidget(self.lp)
        self.split.addWidget(self.canvas)
        self.split.addWidget(self.rp)
        saved_split = UserPrefs.load("splitter_state")
        if saved_split:
            self.split.restoreState(saved_split)
        else:
            self.split.setSizes([220, 1000, 240])
        main_lay.addWidget(self.split, 1)

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

        self.status_history_lbl = QLabel(f"History: 0/{Config.MAX_HISTORY}")
        self.status_history_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT_MUTED}; padding: 0 8px;")
        self.status_history_lbl.setToolTip("Unified Undo/Redo Action Stack Depth")

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
        self.status_bar.addWidget(self.status_history_lbl)
        self.status_bar.addPermanentWidget(self.status_coord_lbl)
        self.status_bar.addPermanentWidget(self.status_dim_lbl)
        self.status_bar.addPermanentWidget(self.status_zoom_btn)
        self.status_bar.addPermanentWidget(self.hw_mon)

        # Connect canvas signals to status bar telemetry
        self.canvas.mouse_moved.connect(lambda x, y: self.status_coord_lbl.setText(f"X: {x}  Y: {y}"))
        self.canvas.zoom_changed.connect(lambda z: self.status_zoom_btn.setText(f"{z}%"))
        self.canvas.images_dropped.connect(self.handle_dropped_images)

        # Standard Studio Menu Bar
        self.setup_menu_bar()
        self.update_history_ui()
        self.canvas.setFocus()

        # Restore window geometry & state
        saved_geom = UserPrefs.load("geometry")
        if saved_geom:
            self.restoreGeometry(saved_geom)
        saved_state = UserPrefs.load("window_state")
        if saved_state:
            self.restoreState(saved_state)

    def setup_menu_bar(self):
        menu_bar = self.menuBar()

        # File Menu
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction("Open Image...", self.on_open_image, QKeySequence("Ctrl+O"))
        file_menu.addAction("Import Folder...", self.on_open_folder, QKeySequence("Ctrl+Shift+O"))
        file_menu.addSeparator()
        file_menu.addAction("Quick Save", self.on_quick_save, QKeySequence("Ctrl+S"))
        file_menu.addAction("Export Image...", self.on_export, QKeySequence("Ctrl+Shift+S"))
        file_menu.addAction("Send to Photopea", self.on_send_to_photopea)
        if os.name == 'nt':
            file_menu.addAction("Send to Photoshop", self.on_send_to_photoshop)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close, QKeySequence("Ctrl+Q"))

        # Edit Menu
        edit_menu = menu_bar.addMenu("&Edit")
        self.act_undo = edit_menu.addAction("Undo", self.on_undo)
        self.act_undo.setShortcuts([QKeySequence("Ctrl+Z"), QKeySequence("Alt+Z")])
        self.act_redo = edit_menu.addAction("Redo", self.on_redo)
        self.act_redo.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y"), QKeySequence("Alt+Shift+Z")])
        edit_menu.addSeparator()
        act_clear = edit_menu.addAction("Deselect / Clear Mask", self.canvas.clear_mask)
        act_clear.setShortcuts([QKeySequence("Ctrl+D"), QKeySequence("Esc")])
        edit_menu.addAction("Invert Mask", self.canvas.invert_mask, QKeySequence("Ctrl+Shift+I"))
        act_expand = edit_menu.addAction("Expand Mask (+3px)", lambda: self.canvas.dilate_mask(3))
        act_expand.setShortcuts([QKeySequence("Shift+>"), QKeySequence(">")])
        act_contract = edit_menu.addAction("Contract Mask (-3px)", lambda: self.canvas.erode_mask(3))
        act_contract.setShortcuts([QKeySequence("Shift+<"), QKeySequence("<")])

        # View Menu
        view_menu = menu_bar.addMenu("&View")
        view_menu.addAction("Fit to Screen", self.canvas.fit_to_screen, QKeySequence("Ctrl+0"))
        view_menu.addAction("Actual Size (100%)", self.canvas.reset_zoom, QKeySequence("Ctrl+1"))
        act_zoom_in = view_menu.addAction("Zoom In (+25%)", lambda: self.canvas.zoom_by(1.25))
        act_zoom_in.setShortcuts([QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")])
        view_menu.addAction("Zoom Out (-20%)", lambda: self.canvas.zoom_by(0.8), QKeySequence("Ctrl+-"))
        view_menu.addSeparator()
        view_menu.addAction("Flip View Horizontal", self.canvas.toggle_flip_horizontal, QKeySequence("H"))
        view_menu.addAction("Toggle Quick Mask", self.canvas.toggle_quick_mask, QKeySequence("Q"))
        view_menu.addAction("Cycle Mask Color", self.canvas.cycle_mask_color, QKeySequence("Ctrl+M"))

        # Help Menu
        help_menu = menu_bar.addMenu("&Help")
        help_menu.addAction("Documentation & Shortcuts", lambda: HelpSystem.show_guide(self), QKeySequence("F1"))

    def setup_shortcuts(self):
        self.tool_controller.setup_shortcuts()

    #/////////////////////////////////#
    #    DELEGATES: TOOL CONTROLLER   #
    #/////////////////////////////////#

    def adjust_brush_size(self, delta: int):
        self.tool_controller.adjust_brush_size(delta)

    def set_tool(self, tool: str):
        self.tool_controller.set_tool(tool)

    def keyPressEvent(self, event):
        self.tool_controller.handle_key_press(event)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        self.tool_controller.handle_key_release(event)
        super().keyReleaseEvent(event)

    #/////////////////////////////////#
    #  DELEGATES: PIPELINE CONTROLLER #
    #/////////////////////////////////#

    def _check_lock_state(self):
        self.pipeline_controller._check_lock_state()

    def _update_queue_ui(self):
        self.pipeline_controller._update_queue_ui()

    def on_worker_progress(self, val):
        self.pipeline_controller.on_worker_progress(val)

    def enqueue_task(self, task: str, path: str, *args):
        self.pipeline_controller.enqueue_task(task, path, *args)

    def _process_queue(self):
        self.pipeline_controller._process_queue()

    def stop_thread(self):
        self.pipeline_controller.stop_thread()

    def on_task_error(self, message: str):
        self.pipeline_controller.on_task_error(message)

    def on_task_finished(self, result, patches):
        self.pipeline_controller.on_task_finished(result, patches)

    def on_ocr_scan(self):
        self.pipeline_controller.on_ocr_scan()

    def on_transparency_scan(self):
        self.pipeline_controller.on_transparency_scan()

    def on_lama_clean(self):
        self.pipeline_controller.on_lama_clean()

    def on_undo(self):
        self.pipeline_controller.on_undo()

    def on_redo(self):
        self.pipeline_controller.on_redo()

    def on_undo_image(self):
        self.pipeline_controller.on_undo_image()

    def on_redo_image(self):
        self.pipeline_controller.on_redo_image()

    def on_undo_mask(self):
        self.pipeline_controller.on_undo_mask()

    def on_redo_mask(self):
        self.pipeline_controller.on_redo_mask()

    def update_history_ui(self):
        can_u = self.history.can_undo() if hasattr(self, 'history') and self.history else False
        can_r = self.history.can_redo() if hasattr(self, 'history') and self.history else False
        count = len(self.history.undo_stack) if hasattr(self, 'history') and self.history else 0
        limit = self.history.limit if hasattr(self, 'history') and self.history else Config.MAX_HISTORY

        if hasattr(self, 'act_undo'):
            self.act_undo.setEnabled(can_u)
        if hasattr(self, 'act_redo'):
            self.act_redo.setEnabled(can_r)
        if hasattr(self, 'status_history_lbl'):
            self.status_history_lbl.setText(f"History: {count}/{limit}")

    #/////////////////////////////////#
    #   DELEGATES: BATCH CONTROLLER   #
    #/////////////////////////////////#

    def on_start_batch(self):
        self.batch_controller.on_start_batch()

    def step_batch(self):
        self.batch_controller.step_batch()

    def finalize_batch(self):
        self.batch_controller.finalize_batch()

    def cancel_batch(self):
        self.batch_controller.cancel_batch()

    #/////////////////////////////////#
    #  DELEGATES: SESSION MANAGER     #
    #/////////////////////////////////#

    def on_open_image(self):
        self.session_manager.on_open_image()

    def on_open_folder(self):
        self.session_manager.on_open_folder()

    def load_single_file(self, path: str):
        self.session_manager.load_single_file(path)

    def load_folder(self, folder_path: str):
        self.session_manager.load_folder(folder_path)

    def load_files(self, file_paths: list):
        self.session_manager.load_files(file_paths)

    def handle_dropped_images(self, paths: list):
        self.session_manager.handle_dropped_images(paths)

    def navigate_file(self, direction: int):
        self.session_manager.navigate_file(direction)

    def dragEnterEvent(self, event):
        self.session_manager.dragEnterEvent(event)

    def dragMoveEvent(self, event):
        self.session_manager.dragMoveEvent(event)

    def dropEvent(self, event):
        self.session_manager.dropEvent(event)

    def mark_current_modified(self):
        self.session_manager.mark_current_modified()

    def on_file_clicked(self, it):
        self.session_manager.on_file_clicked(it)

    def on_quick_save(self):
        self.session_manager.on_quick_save()

    def on_export(self, fmt=None):
        self.session_manager.on_export(fmt)

    def on_send_to_photopea(self):
        self.session_manager.on_send_to_photopea()

    def on_send_to_photoshop(self):
        self.session_manager.on_send_to_photoshop()

    #/////////////////////////////////#
    #    UI HELPERS & TELEMETRY       #
    #/////////////////////////////////#

    def toggle_all_files(self, checked: bool):
        """Checks or unchecks all files in the list."""
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(state)

    def show_toast(self, message: str, level: str = "info", duration: int = 3000):
        if hasattr(self, 'toast'):
            self.toast.show_toast(message, level, duration)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'toast') and self.toast.isVisible():
            x = self.width() - self.toast.width() - 24
            y = self.height() - self.toast.height() - 36
            self.toast.move(x, y)

    def update_telemetry(self):
        ram, gpu = self.monitor.get_stats()
        self.hw_mon.lbl.setText(f"{'GPU' if gpu else 'CPU'} | RAM: {ram}MB")
        self.hw_mon.bar.setValue(min(ram // 40, 100))

    def closeEvent(self, event):
        """Ensures clean shutdown of background workers, threads, timers, and process pools."""
        if self.is_batching or self.worker_thread is not None:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "AI processing or batch operation is currently active.\nDo you want to stop and exit anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return

        # Stop telemetry polling
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()

        # Stop batching state
        if hasattr(self, 'batch_controller'):
            self.batch_controller.is_batching = False

        # Cleanly stop QThread worker
        if hasattr(self, 'pipeline_controller') and self.pipeline_controller.worker_thread:
            self.pipeline_controller.stop_thread()

        # Cleanly shut down ProcessPoolExecutor
        try:
            from src.backend.workers import shutdown_pool
            shutdown_pool()
        except Exception as e:
            logger.warning(f"Error during pool shutdown: {e}")

        # Persist user preferences and layout
        try:
            UserPrefs.save("geometry", self.saveGeometry())
            UserPrefs.save("window_state", self.saveState())
            if hasattr(self, 'split'):
                UserPrefs.save("splitter_state", self.split.saveState())
            if hasattr(self, 'b_slider'):
                UserPrefs.save("brush_size", self.b_slider.slider.value())
            if hasattr(self, 'o_slider'):
                UserPrefs.save("mask_opacity", self.o_slider.slider.value())
            if hasattr(self, 't_slider'):
                UserPrefs.save("tile_size", self.t_slider.slider.value() * 512)
            UserPrefs.sync()
        except Exception as e:
            logger.warning(f"Error saving user preferences: {e}")

        logger.info("--- STUDIO SHUTDOWN COMPLETE ---")
        super().closeEvent(event)