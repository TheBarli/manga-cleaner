import os
import cv2
import tempfile
import numpy as np
from src.utils.logger import logger

#/////////////////////////////////#
#     PHOTOSHOP COM INTEROP       #
#/////////////////////////////////#

class PhotoshopBridge:
    @staticmethod
    def _get_photoshop_connection():
        if os.name != 'nt':
            raise Exception("Photoshop Bridge is only available on Windows.")
            
        import win32com.client
        import winreg

        # 1. Try the standard official version-independent ProgID first
        candidates = ["Photoshop.Application"]

        # 2. Add versioned ProgIDs (e.g. Photoshop.Application.170, Photoshop.Application.160)
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "") as hkcr:
                num_keys = winreg.QueryInfoKey(hkcr)[0]
                for i in range(num_keys):
                    key_name = winreg.EnumKey(hkcr, i)
                    # Only accept true application ProgIDs like 'Photoshop.Application.170'
                    # Ignore subkeys like 'Photoshop.Application.170.1'
                    parts = key_name.split('.')
                    if len(parts) in [2, 3] and parts[0] == "Photoshop" and parts[1] == "Application":
                        if key_name not in candidates:
                            candidates.append(key_name)
        except Exception as e:
            logger.warning(f"Registry scan notice: {e}")

        logger.info(f"[i] Testing Photoshop COM ProgIDs: {candidates}")

        for prog_id in candidates:
            try:
                ps = win32com.client.Dispatch(prog_id)
                # Verify that the object actually has Photoshop's Application interface
                _ = ps.Version
                logger.info(f"[+] Successfully connected to Photoshop via: {prog_id}")
                return ps
            except Exception:
                continue

        raise Exception("Could not establish a COM connection to Adobe Photoshop. Ensure Photoshop is installed.")

    @staticmethod
    def send_to_ps(original_rgb: np.ndarray, cleaned_rgb: np.ndarray) -> str:
        """Single page transfer (Manual Mode)"""
        try:
            ps = PhotoshopBridge._get_photoshop_connection()
            
            temp_path = tempfile.gettempdir()
            orig_file = os.path.abspath(os.path.join(temp_path, "mc_transfer_orig.png"))
            clean_file = os.path.abspath(os.path.join(temp_path, "mc_transfer_clean.png"))
            
            # Save temporary transfer images
            if len(original_rgb.shape) == 3 and original_rgb.shape[2] == 4:
                cv2.imwrite(orig_file, cv2.cvtColor(original_rgb, cv2.COLOR_RGBA2BGRA))
            else:
                cv2.imwrite(orig_file, cv2.cvtColor(original_rgb, cv2.COLOR_RGB2BGR))

            if len(cleaned_rgb.shape) == 3 and cleaned_rgb.shape[2] == 4:
                cv2.imwrite(clean_file, cv2.cvtColor(cleaned_rgb, cv2.COLOR_RGBA2BGRA))
            else:
                cv2.imwrite(clean_file, cv2.cvtColor(cleaned_rgb, cv2.COLOR_RGB2BGR))

            # Open Original Document
            orig_doc = ps.Open(orig_file)
            try:
                orig_doc.ActiveLayer.Name = "Original"
            except Exception:
                pass

            # Open Cleaned, Copy pixels, and Close it
            clean_doc = ps.Open(clean_file)
            clean_doc.Selection.SelectAll()
            clean_doc.Selection.Copy()
            clean_doc.Close(2) # 2 = DoNotSaveChanges

            # Paste into the Original Document
            orig_doc.Paste()
            try:
                orig_doc.ActiveLayer.Name = "MangaCleaner_Result"
            except Exception:
                pass

            return "Success"

        except Exception as e:
            logger.error(f"[X] Photoshop Bridge Exception: {e}", exc_info=True)
            return str(e)

    @staticmethod
    def open_batch_in_ps(orig_paths: list, clean_dir: str):
        """Opens entire batch as layers after AI finishes"""
        try:
            ps = PhotoshopBridge._get_photoshop_connection()
            logger.info(f"[+] Initializing Photoshop Batch for {len(orig_paths)} pages...")

            for i, orig_path in enumerate(orig_paths):
                abs_orig = os.path.abspath(orig_path)
                doc = ps.Open(abs_orig)
                try:
                    doc.ActiveLayer.Name = f"Page_{i+1}_Original"
                except Exception:
                    pass
                
                clean_name = os.path.splitext(os.path.basename(orig_path))[0] + "_cleaned.jpg"
                clean_path = os.path.abspath(os.path.join(clean_dir, clean_name))
                
                if os.path.exists(clean_path):
                    clean_doc = ps.Open(clean_path)
                    clean_doc.Selection.SelectAll()
                    clean_doc.Selection.Copy()
                    clean_doc.Close(2)
                    
                    doc.Paste()
                    try:
                        doc.ActiveLayer.Name = f"Page_{i+1}_Cleaned"
                    except Exception:
                        pass
                
                logger.info(f"    - Page {i+1} merged in PS")
            
            return True
        except Exception as e:
            logger.error(f"[X] Photoshop Batch Failed: {e}")
            return False