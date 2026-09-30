import os
import cv2
import tempfile
import webbrowser
import json
import threading
import http.server
import socketserver
import urllib.parse
import shutil
from src.utils.logger import logger

#/////////////////////////////////#
#     PHOTOPEA WEB API BRIDGE     #
#/////////////////////////////////#

class PhotopeaBridge:
    _httpd = None
    _port = 0
    _session_dir = os.path.join(tempfile.gettempdir(), "mc_photopea_session")

    @staticmethod
    def _safe_open_browser(url):
        """
        Safely opens the system browser by temporarily removing PyInstaller's 
        poisoned LD_LIBRARY_PATH so the host's /bin/sh doesn't crash.
        """
        env_copy = os.environ.copy()
        
        # Restore original path if PyInstaller backed it up, otherwise just delete it
        if 'LD_LIBRARY_PATH_ORIG' in os.environ:
            os.environ['LD_LIBRARY_PATH'] = os.environ['LD_LIBRARY_PATH_ORIG']
        elif 'LD_LIBRARY_PATH' in os.environ:
            del os.environ['LD_LIBRARY_PATH']
            
        try:
            webbrowser.open(url)
        finally:
            # Restore the poisoned PyInstaller environment so the rest of the app doesn't crash
            os.environ.clear()
            os.environ.update(env_copy)

    @staticmethod
    def _start_server():
        """Spins up a background server to feed images securely to Photopea"""
        if PhotopeaBridge._httpd is not None:
            return

        # Create a dedicated directory to serve images with their real filenames
        if not os.path.exists(PhotopeaBridge._session_dir):
            os.makedirs(PhotopeaBridge._session_dir)

        class CORSImageHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=PhotopeaBridge._session_dir, **kwargs)
                
            def end_headers(self):
                # This CORS header is strictly required by the Photopea API
                self.send_header('Access-Control-Allow-Origin', '*')
                super().end_headers()
                
            def log_message(self, format, *args):
                pass # Suppress HTTP logs to keep the console clean

        PhotopeaBridge._httpd = socketserver.TCPServer(("127.0.0.1", 0), CORSImageHandler)
        PhotopeaBridge._port = PhotopeaBridge._httpd.server_address[1]
        
        threading.Thread(target=PhotopeaBridge._httpd.serve_forever, daemon=True).start()
        logger.info(f"[+] Local Image Server started for Photopea on port {PhotopeaBridge._port}")

    @staticmethod
    def _clear_session():
        """Removes old images from the session directory"""
        if not os.path.exists(PhotopeaBridge._session_dir): return
        for f in os.listdir(PhotopeaBridge._session_dir):
            try: os.remove(os.path.join(PhotopeaBridge._session_dir, f))
            except: pass

    @staticmethod
    def _get_processor_script():
        """
        Photopea executes this script AFTER EVERY SINGLE FILE is loaded.
        This handles asynchronous race conditions (e.g. if the cleaned 
        image finishes downloading before the original does).
        """
        return """
        var current = app.activeDocument;
        var name = current.name;
        var isClean = name.indexOf("_cleaned") !== -1;
        
        var origName = isClean ? name.replace("_cleaned", "") : name;
        var extIndex = name.lastIndexOf(".");
        var cleanName = isClean ? name : name.substring(0, extIndex) + "_cleaned" + name.substring(extIndex);

        var origDoc = null;
        var cleanDoc = null;
        
        // Check if both the Original and Cleaned pairs have finished loading
        for(var i = 0; i < app.documents.length; i++) {
            if(app.documents[i].name === origName) origDoc = app.documents[i];
            if(app.documents[i].name === cleanName) cleanDoc = app.documents[i];
        }
        
        // Only merge if both files are fully loaded into the workspace
        if(origDoc && cleanDoc) {
            app.activeDocument = cleanDoc;
            cleanDoc.selection.selectAll();
            cleanDoc.selection.copy();
            
            app.activeDocument = origDoc;
            origDoc.paste();
            origDoc.activeLayer.name = "Cleaned";
            origDoc.layers[origDoc.layers.length - 1].name = "Original";
            
            cleanDoc.close();
        }
        """

    @staticmethod
    def send_to_photopea(original_rgb, cleaned_rgb, img_path=None):
        """Single page transfer"""
        try:
            PhotopeaBridge._start_server()
            PhotopeaBridge._clear_session()

            orig_bgr = cv2.cvtColor(original_rgb, cv2.COLOR_RGBA2BGRA if original_rgb.shape[2] == 4 else cv2.COLOR_RGB2BGR)
            clean_bgr = cv2.cvtColor(cleaned_rgb, cv2.COLOR_RGBA2BGRA if cleaned_rgb.shape[2] == 4 else cv2.COLOR_RGB2BGR)
            
            # Extract the real filename so Photopea tabs are labeled correctly
            if img_path:
                base_name = os.path.basename(img_path)
                name_part, _ = os.path.splitext(base_name)
                orig_name = f"{name_part}.png"
                clean_name = f"{name_part}_cleaned.png"
            else:
                orig_name = "Image.png"
                clean_name = "Image_cleaned.png"

            cv2.imwrite(os.path.join(PhotopeaBridge._session_dir, orig_name), orig_bgr)
            cv2.imwrite(os.path.join(PhotopeaBridge._session_dir, clean_name), clean_bgr)

            v_orig = urllib.parse.quote(orig_name)
            v_clean = urllib.parse.quote(clean_name)

            files = [
                f"http://127.0.0.1:{PhotopeaBridge._port}/{v_orig}",
                f"http://127.0.0.1:{PhotopeaBridge._port}/{v_clean}"
            ]

            payload = {
                "files": files,
                "environment": {"theme": 2, "intro": False},
                "script": PhotopeaBridge._get_processor_script()
            }

            encoded_json = urllib.parse.quote(json.dumps(payload))
            PhotopeaBridge._safe_open_browser(f"https://www.photopea.com#{encoded_json}")
            return "Success"

        except Exception as e:
            logger.error(f"[X] Photopea Bridge Exception: {e}", exc_info=True)
            return str(e)

    @staticmethod
    def open_batch_in_photopea(orig_paths, clean_dir):
        """Batch transfer for multiple chapters"""
        try:
            PhotopeaBridge._start_server()
            PhotopeaBridge._clear_session()
            
            files = []
            logger.info(f"[+] Initializing Photopea Batch for {len(orig_paths)} pages...")

            for orig_path in orig_paths:
                orig_name = os.path.basename(orig_path)
                clean_name = os.path.splitext(orig_name)[0] + "_cleaned.png"
                clean_path = os.path.join(clean_dir, clean_name)

                if not os.path.exists(clean_path): continue

                # Copy files using their REAL names to the session directory
                shutil.copy(orig_path, os.path.join(PhotopeaBridge._session_dir, orig_name))
                shutil.copy(clean_path, os.path.join(PhotopeaBridge._session_dir, clean_name))

                # URL-encode the filenames in case they have spaces
                v_orig = urllib.parse.quote(orig_name)
                v_clean = urllib.parse.quote(clean_name)

                files.append(f"http://127.0.0.1:{PhotopeaBridge._port}/{v_orig}")
                files.append(f"http://127.0.0.1:{PhotopeaBridge._port}/{v_clean}")

            payload = {
                "files": files,
                "environment": {"theme": 2, "intro": False},
                "script": PhotopeaBridge._get_processor_script()
            }

            encoded_json = urllib.parse.quote(json.dumps(payload))
            PhotopeaBridge._safe_open_browser(f"https://www.photopea.com#{encoded_json}")
            return True

        except Exception as e:
            logger.error(f"[X] Photopea Batch Failed: {e}", exc_info=True)
            return False
