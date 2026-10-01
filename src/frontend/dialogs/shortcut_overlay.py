from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QGridLayout, QScrollArea, QWidget, QFrame)
from PySide6.QtCore import Qt
from src.utils.config import Config


#/////////////////////////////////#
#   SHORTCUTS OVERLAY MODAL       #
#/////////////////////////////////#

class ShortcutOverlayDialog(QDialog):
    """
    Transparent modal overlay displaying categorized keyboard shortcuts.
    Activated via Ctrl+/ or ? for rapid workflow reference.
    """

    CATEGORIES = [
        ("Tools", [
            ("B", "Brush Tool"),
            ("E", "Eraser Tool"),
            ("R", "Rectangle Selection"),
            ("L", "Lasso Tool"),
            ("P", "Polygonal Selection"),
            ("G", "Bucket Fill"),
            ("M", "Move / Pan Canvas"),
            ("Hold Space", "Temporary Hand Tool"),
            ("Hold Alt", "Quick Invert Tool"),
            ("Shift + Click", "Draw Straight Line"),
            ("Double Click", "Commit Polygon"),
        ]),
        ("AI & Cleaning", [
            ("O", "Auto-Detect Text (OCR)"),
            ("T", "Transparency Scan"),
            ("C", "Execute AI Clean"),
            ("\\", "Hold for Image Comparison"),
        ]),
        ("Mask Operations", [
            ("Ctrl + D / Esc", "Clear Mask"),
            ("Ctrl + Shift + I", "Invert Mask"),
            ("Shift + >", "Expand Mask (+3px)"),
            ("Shift + <", "Contract Mask (-3px)"),
            ("Q", "Toggle Quick Mask"),
            ("Ctrl + M", "Cycle Mask Tint"),
        ]),
        ("Canvas & View", [
            ("Ctrl + 0", "Fit to Screen"),
            ("Ctrl + 1", "Actual Size (100%)"),
            ("Ctrl + + / =", "Zoom In (+25%)"),
            ("Ctrl + -", "Zoom Out (-20%)"),
            ("H", "Flip View Horizontal"),
            ("[ / ]", "Brush Size (-/+ 5px)"),
            ("Shift + [ / ]", "Brush Size (-/+ 20px)"),
            ("Alt + RClick Drag", "Interactive Brush Sizing"),
        ]),
        ("History & Navigation", [
            ("Ctrl + Z", "Undo Action"),
            ("Ctrl + Shift + Z", "Redo Action"),
            ("Ctrl + Y", "Redo Action"),
            ("PgUp / Ctrl+Left", "Previous Page"),
            ("PgDn / Ctrl+Right", "Next Page"),
        ]),
        ("File & General", [
            ("Ctrl + O", "Open Image"),
            ("Ctrl + Shift + O", "Import Folder"),
            ("Ctrl + S", "Quick Save"),
            ("Ctrl + Shift + S", "Export Image"),
            ("F1", "Full Documentation"),
            ("Ctrl + / or ?", "Shortcuts Cheat Sheet"),
        ]),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(780, 520)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(12, 12, 12, 12)

        # Card container with semi-transparent obsidian background
        card = QFrame()
        card.setObjectName("ShortcutCard")
        card.setStyleSheet(f"""
            #ShortcutCard {{
                background-color: rgba(28, 28, 32, 0.96);
                border: 1px solid #4a4a50;
                border-radius: 8px;
            }}
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(20, 16, 20, 20)
        card_lay.setSpacing(14)

        # Header bar
        header_lay = QHBoxLayout()
        title_lbl = QLabel("⌨️  Keyboard Shortcuts")
        title_lbl.setStyleSheet(f"color: {Config.COLOR_ACCENT}; font-size: 15px; font-weight: bold; letter-spacing: 0.5px;")

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #888888;
                font-size: 14px;
                font-weight: bold;
                border-radius: 14px;
            }
            QPushButton:hover {
                background: #3a3a40;
                color: #ffffff;
            }
        """)
        close_btn.clicked.connect(self.close)

        header_lay.addWidget(title_lbl)
        header_lay.addStretch()
        header_lay.addWidget(close_btn)
        card_lay.addLayout(header_lay)

        # Content in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        grid_lay = QGridLayout(scroll_widget)
        grid_lay.setHorizontalSpacing(24)
        grid_lay.setVerticalSpacing(18)
        grid_lay.setContentsMargins(0, 4, 0, 0)

        # 3 columns of categories
        for idx, (cat_name, shortcuts) in enumerate(self.CATEGORIES):
            col = idx % 3
            row = idx // 3

            cat_box = QVBoxLayout()
            cat_box.setSpacing(6)

            cat_title = QLabel(cat_name.upper())
            cat_title.setStyleSheet("color: #e0e0e0; font-size: 11px; font-weight: bold; letter-spacing: 1px; border-bottom: 1px solid #3d3d42; padding-bottom: 4px;")
            cat_box.addWidget(cat_title)

            for key, desc in shortcuts:
                row_lay = QHBoxLayout()
                row_lay.setSpacing(8)

                key_badge = QLabel(key)
                key_badge.setStyleSheet("""
                    background-color: #242428;
                    color: #dcdcdc;
                    border: 1px solid #3c3c44;
                    border-radius: 3px;
                    padding: 2px 6px;
                    font-size: 10px;
                    font-weight: 600;
                    font-family: 'Segoe UI', monospace;
                """)

                desc_lbl = QLabel(desc)
                desc_lbl.setStyleSheet("color: #a0a0a8; font-size: 11px;")

                row_lay.addWidget(key_badge)
                row_lay.addWidget(desc_lbl)
                row_lay.addStretch()
                cat_box.addLayout(row_lay)

            cat_box.addStretch()
            grid_lay.addLayout(cat_box, row, col)

        scroll.setWidget(scroll_widget)
        card_lay.addWidget(scroll)

        # Footer hint
        footer_lbl = QLabel("Press Esc or click ✕ to close")
        footer_lbl.setStyleSheet("color: #66666e; font-size: 10px; text-align: center;")
        footer_lbl.setAlignment(Qt.AlignCenter)
        card_lay.addWidget(footer_lbl)

        main_lay.addWidget(card)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Slash, Qt.Key_Question):
            self.close()
        else:
            super().keyPressEvent(event)
