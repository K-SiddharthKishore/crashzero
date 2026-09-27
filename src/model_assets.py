"""Download official detector weights on hosted first use, atomically and once."""
import threading
import urllib.request
from config.settings import MODEL

_lock = threading.Lock()
MODEL_URL = 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt'

def ensure_model():
    with _lock:
        if MODEL.exists(): return MODEL
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        temporary = MODEL.with_suffix('.download')
        try:
            with urllib.request.urlopen(MODEL_URL, timeout=60) as response, temporary.open('wb') as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            if temporary.stat().st_size < 1024 * 1024:
                raise ValueError('Detector download was incomplete')
            temporary.replace(MODEL)
        finally:
            temporary.unlink(missing_ok=True)
        return MODEL
