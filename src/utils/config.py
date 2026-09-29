import json
import os
from src.utils.paths import Paths

#/////////////////////////////////#
#    GLOBAL STUDIO CONFIGURATION  #
#/////////////////////////////////#

class Config:
    APP_NAME = "MANGA-CLEANER"
    VERSION = "3.2.0"

    # Adobe Illustrator (Spectrum Dark) Design Tokens
    COLOR_BG_BASE = "#262626"
    COLOR_BG_PANEL = "#323232"
    COLOR_BG_SURFACE = "#3d3d3d"
    COLOR_BG_HOVER = "#4a4a4a"
    COLOR_BORDER_SUBTLE = "#222222"
    COLOR_BORDER_ACTIVE = "#ff9a00"
    COLOR_ACCENT = "#ff9a00"
    COLOR_ACCENT_HOVER = "#ffad33"
    COLOR_ACCENT_SUBTLE = "#3f3525"
    COLOR_TEXT = "#f5f5f5"
    COLOR_TEXT_PRIMARY = COLOR_TEXT
    COLOR_TEXT_MUTED = "#b8b8b8"
    COLOR_TEXT_DIM = "#7a7a7a"

    # Status Colors (Restrained Palette)
    COLOR_SUCCESS = "#22c55e"
    COLOR_READY = COLOR_SUCCESS
    COLOR_MODIFIED = "#ff9a00"
    COLOR_WAITING = "#f59e0b"
    COLOR_ERROR = "#f43f5e"

    # Backward compatibility aliases
    COLOR_BG = COLOR_BG_BASE
    COLOR_PANEL = COLOR_BG_PANEL
    
    DEFAULT_BRUSH_SIZE = 40
    MAX_HISTORY = 20
    DEFAULT_TILE_WIDTH = 1024 

    _ID_FILE = os.path.join(Paths.CACHE, "batch_id.json")

    @staticmethod
    def get_next_batch_id():
        current_id = 1
        if os.path.exists(Config._ID_FILE):
            try:
                with open(Config._ID_FILE, 'r') as f:
                    data = json.load(f)
                    current_id = data.get("last_id", 0) + 1
            except:
                pass
        
        if current_id > 65535:
            current_id = 1
            
        with open(Config._ID_FILE, 'w') as f:
            json.dump({"last_id": current_id}, f)
            
        return f"batch_{current_id:05d}"
