import psutil
import os

#/////////////////////////////////#
#     APP-SPECIFIC TELEMETRY      #
#/////////////////////////////////#

class SystemMonitor:
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            self._gpu_active = 1 if 'CUDAExecutionProvider' in providers else 0
        except Exception:
            self._gpu_active = 0

    def get_stats(self):
        """Returns (app_ram_mb, is_gpu_active)"""
        ram_bytes = self.process.memory_info().rss
        ram_mb = int(ram_bytes / (1024 * 1024))
        return ram_mb, self._gpu_active

    @staticmethod
    def get_detailed_specs():
        """Calculates requirements based on local hardware"""
        import onnxruntime as ort

        total_ram = round(psutil.virtual_memory().total / (1024**3), 1)
        
        gpu_label = "CPU ONLY (Slow Mode)"
        providers = ort.get_available_providers()
        if 'CUDAExecutionProvider' in providers:
            gpu_label = "NVIDIA CUDA (High Speed)"
            
        return {
            "ram": total_ram,
            "engine": gpu_label,
            "os": os.name.upper()
        }
