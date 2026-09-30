"""Local device, file and RTSP/HTTP input; stream secrets never enter metadata."""
from dataclasses import dataclass, asdict
from pathlib import Path
import math
import time
import threading
import queue
import cv2

@dataclass
class Camera:
    camera_id: str = 'DEMO'
    name: str = 'Demo camera'
    location: str = 'LOCATION NOT CONFIGURED'
    latitude: float | None = None
    longitude: float | None = None
    def metadata(self): return asdict(self)

class VideoSource:
    live = False
    def __init__(self, source):
        self.source = source
        self.capture = None
    def open(self):
        self.capture = cv2.VideoCapture(self.source)
        if not self.capture.isOpened():
            self.close()
            raise ValueError('Camera or video unavailable. Check the source and camera permission.')
        fps = self.capture.get(cv2.CAP_PROP_FPS)
        self.fps = fps if math.isfinite(fps) and 0 < fps <= 240 else 25.
        self.index = 0; self.started = time.monotonic()
        if self.live: self._start_live_reader()
        return self
    def _start_live_reader(self):
        self.latest=queue.Queue(maxsize=1); self.capture_stop=threading.Event()
        self.reader=threading.Thread(target=self._capture_loop,daemon=True,name='CrashZero-capture')
        self.reader.start()
    def _capture_loop(self):
        try:
            while not self.capture_stop.is_set():
                ok,frame=self.capture.read()
                item=(time.monotonic()-self.started,frame) if ok else None
                try: self.latest.get_nowait()
                except queue.Empty: pass
                try: self.latest.put_nowait(item)
                except queue.Full: pass
                if not ok: break
        finally: self.capture.release()
    def read(self):
        if self.live:
            try: return self.latest.get(timeout=6)
            except queue.Empty: return None
        ok,frame = self.capture.read()
        if not ok: return None
        t = time.monotonic()-self.started if self.live else self.index/self.fps
        self.index += 1
        return t,frame
    def close(self):
        if hasattr(self,'capture_stop'):
            self.capture_stop.set()
            self.reader.join(timeout=4)
        elif self.capture is not None: self.capture.release()

class VideoFileSource(VideoSource):
    def __init__(self, path): super().__init__(str(Path(path)))

class WebcamSource(VideoSource):
    live = True
    def __init__(self, index=0): super().__init__(int(index))

class StreamSource(VideoSource):
    live = True
    def __init__(self, url, *, hosted=False):
        from src.video.stream_config import validate_stream_url
        super().__init__(validate_stream_url(url,hosted=hosted))
    def open(self):
        # FFmpeg bounded network reads prevent a disconnected stream hanging the worker.
        self.capture = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,5000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,3000])
        if not self.capture.isOpened():
            self.close(); raise ValueError('Stream unavailable. Check the local URL and network.')
        self.fps = 25.; self.index = 0; self.started = time.monotonic()
        if self.live: self._start_live_reader()
        return self
