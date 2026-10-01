from PySide6.QtWidgets import (QDialog, QComboBox, QVBoxLayout,
                             QHBoxLayout, QLabel, QFrame, QPushButton)
from PySide6.QtCore import Qt
from src.utils.config import Config


#/////////////////////////////////#
#    BATCH SETUP DIALOG MODAL     #
#/////////////////////////////////#

class BatchSetupDialog(QDialog):
    """
    Configuration modal for batch cleaning and export operations.
    Provides live mode descriptions, export explanations, and selected file count telemetry.
    """
    SCAN_DESCRIPTIONS = {
        "OCR Scan": "Auto-detect speech text bubbles using AI and inpaint detected regions.",
        "Transparency Scan": "Scan for transparent pixel boundaries in layered manga panels.",
        "Mask": "Use manually drawn brush/lasso masks stored in each image's session.",
        "none": "Bypass detection phase (cleans existing masks or skips to export)."
    }

    EXPORT_DESCRIPTIONS = {
        "png": "Lossless PNG format with full transparency preservation (recommended).",
        "jpg": "Standard JPEG format with balanced compression for smaller file size.",
        "none": "Keep cleaned images in active session memory without saving to disk."
    }

    def __init__(self, parent=None, selected_count: int = 0, total_count: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Batch Processing Setup")
        self.setMinimumWidth(440)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Config.COLOR_PANEL};
                color: {Config.COLOR_TEXT};
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }}
            QComboBox {{
                background-color: {Config.COLOR_BG};
                color: {Config.COLOR_TEXT};
                border: 1px solid {Config.COLOR_BORDER_SUBTLE};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                min-height: 24px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Config.COLOR_BG};
                color: {Config.COLOR_TEXT};
                selection-background-color: {Config.COLOR_ACCENT};
                border: 1px solid {Config.COLOR_BORDER_SUBTLE};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Title / Header
        title_lbl = QLabel("BATCH CLEAN & EXPORT")
        title_lbl.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-size: 13px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(title_lbl)

        # Section 1: Detection Mode
        sec1_lay = QVBoxLayout()
        sec1_lay.setSpacing(4)
        sec1_lbl = QLabel("Detection Mode:")
        sec1_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT}; font-weight: 600; font-size: 11px;")
        sec1_lay.addWidget(sec1_lbl)

        self.scan_mode = QComboBox()
        self.scan_mode.addItems(["OCR Scan", "Transparency Scan", "Mask", "none"])
        sec1_lay.addWidget(self.scan_mode)

        self.scan_desc_lbl = QLabel(self.SCAN_DESCRIPTIONS["OCR Scan"])
        self.scan_desc_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT_MUTED}; font-size: 10px; margin-top: 2px;")
        self.scan_desc_lbl.setWordWrap(True)
        sec1_lay.addWidget(self.scan_desc_lbl)
        self.scan_mode.currentTextChanged.connect(self._on_scan_mode_changed)
        layout.addLayout(sec1_lay)

        # Section 2: Export Format
        sec2_lay = QVBoxLayout()
        sec2_lay.setSpacing(4)
        sec2_lbl = QLabel("Export Format:")
        sec2_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT}; font-weight: 600; font-size: 11px;")
        sec2_lay.addWidget(sec2_lbl)

        self.export_fmt = QComboBox()
        self.export_fmt.addItems(["png", "jpg", "none"])
        sec2_lay.addWidget(self.export_fmt)

        self.export_desc_lbl = QLabel(self.EXPORT_DESCRIPTIONS["png"])
        self.export_desc_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT_MUTED}; font-size: 10px; margin-top: 2px;")
        self.export_desc_lbl.setWordWrap(True)
        sec2_lay.addWidget(self.export_desc_lbl)
        self.export_fmt.currentTextChanged.connect(self._on_export_fmt_changed)
        layout.addLayout(sec2_lay)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"border: none; border-top: 1px solid {Config.COLOR_BORDER_SUBTLE};")
        layout.addWidget(sep)

        # File selection summary counter
        if selected_count > 0:
            files_text = f"Files: {selected_count} selected (of {total_count} total)"
        elif total_count > 0:
            files_text = f"Files: All {total_count} files will be processed"
        else:
            files_text = "Files: No files loaded"
        self.files_lbl = QLabel(files_text)
        self.files_lbl.setStyleSheet(f"color: {Config.COLOR_TEXT}; font-size: 11px; font-weight: 500;")
        layout.addWidget(self.files_lbl)

        # Dialog Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {Config.COLOR_BORDER_SUBTLE};
                color: {Config.COLOR_TEXT};
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {Config.COLOR_BG};
            }}
        """)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_start = QPushButton("Start Batch")
        self.btn_start.setStyleSheet(f"""
            QPushButton {{
                background-color: {Config.COLOR_ACCENT};
                border: none;
                color: #ffffff;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 20px;
            }}
            QPushButton:hover {{
                background-color: {Config.COLOR_ACCENT_HOVER};
            }}
        """)
        self.btn_start.clicked.connect(self.accept)

        btn_box.addWidget(self.btn_cancel)
        btn_box.addWidget(self.btn_start)
        layout.addLayout(btn_box)

    def _on_scan_mode_changed(self, text: str):
        self.scan_desc_lbl.setText(self.SCAN_DESCRIPTIONS.get(text, ""))

    def _on_export_fmt_changed(self, text: str):
        self.export_desc_lbl.setText(self.EXPORT_DESCRIPTIONS.get(text, ""))

    def get_results(self):
        return self.scan_mode.currentText(), self.export_fmt.currentText()
