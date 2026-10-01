import os
import cv2
import numpy as np
from src.utils.logger import logger

def safe_imwrite(path: str, img: np.ndarray, ext: str = None) -> bool:
    """Unicode-safe image writer that avoids cv2.imwrite() ASCII path limitations on Windows.
    
    Encodes the OpenCV image buffer in memory and writes it to disk using NumPy's tofile(),
    which safely handles CJK, Japanese, and arbitrary Unicode characters in file paths.
    """
    try:
        if ext is None:
            ext = os.path.splitext(path)[1].lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        success, buf = cv2.imencode(ext, img)
        if success:
            buf.tofile(path)
            return True
        logger.error(f"Failed to encode image buffer for: {path}")
        return False
    except Exception as e:
        logger.error(f"safe_imwrite failed for {path}: {e}")
        return False

def safe_imread(path: str, flags: int = cv2.IMREAD_UNCHANGED) -> np.ndarray:
    """Unicode-safe image reader using np.fromfile and cv2.imdecode."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if len(data) == 0:
            return None
        return cv2.imdecode(data, flags)
    except Exception as e:
        logger.error(f"safe_imread failed for {path}: {e}")
        return None
