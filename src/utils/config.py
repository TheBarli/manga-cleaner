import json
import os
from src.utils.paths import Paths

#/////////////////////////////////#
#    GLOBAL STUDIO CONFIGURATION  #
#/////////////////////////////////#

class Config:
    APP_NAME = "MANGA-CLEANER"
    VERSION = "3.2.0"

    # Modern Studio Design Tokens
    COLOR_BG_BASE = "#0d0e12"
    COLOR_BG_PANEL = "#14161c"
    COLOR_BG_SURFACE = "#1b1e26"
    COLOR_BG_HOVER = "#252934"
    COLOR_BORDER_SUBTLE = "#232732"
    COLOR_BORDER_ACTIVE = "#3a4052"
    COLOR_ACCENT = "#3b82f6"
    COLOR_ACCENT_HOVER = "#60a5fa"
    COLOR_ACCENT_SUBTLE = "#1e293b"
    COLOR_TEXT = "#f1f5f9"
    COLOR_TEXT_PRIMARY = COLOR_TEXT
    COLOR_TEXT_MUTED = "#94a3b8"
    COLOR_TEXT_DIM = "#64748b"

    # Semantic Status Colors
    COLOR_SUCCESS = "#10b981"
    COLOR_READY = COLOR_SUCCESS
    COLOR_MODIFIED = "#38bdf8"
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
