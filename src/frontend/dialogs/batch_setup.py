from PySide6.QtWidgets import (QDialog, QComboBox, QDialogButtonBox, QFormLayout)
from src.utils.config import Config


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
        self.export_fmt.addItems(["none", "png", "jpg"])
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
