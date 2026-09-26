from collections import deque
from dataclasses import dataclass, field
import numpy as np
from config.settings import HISTORY_SECONDS, MIN_HISTORY_SECONDS, MIN_OBSERVATIONS, MAX_TRACK_GAP
from src.motion import estimate

@dataclass
class Track:
    id: int
    cls: str
    box: list
    confidence: float
    last_seen: float
    history: deque = field(default_factory=lambda: deque(maxlen=120))
    smoothed_history: deque = field(default_factory=lambda: deque(maxlen=120))
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2))
    position: np.ndarray = field(default_factory=lambda: np.zeros(2))
    stability: float = 0.
    ready: bool = False
    @property
    def radius(self):
        # Conservative image footprint; not metric distance or a calibrated envelope.
        return max(7., min(self.box[2]-self.box[0], self.box[3]-self.box[1]) * .42)
    def project(self, seconds):
        return self.position + self.velocity * seconds

class TrajectoryStore:
    def __init__(self):
        self.tracks = {}
    def update(self, detections, timestamp):
        active = {}
        for d in detections:
            tid = d['id']
            tr = self.tracks.get(tid)
            if tr is None or timestamp - tr.last_seen > MAX_TRACK_GAP:
                tr = Track(tid, d['class'], d['box'], d['confidence'], timestamp)
                self.tracks[tid] = tr
            # Reject duplicate timestamps and reset a trajectory after an implausible
            # detector jump; never reinterpret an ID jump as vehicle acceleration.
            if tr.history and timestamp <= tr.last_seen:
                continue
            if tr.history:
                previous = np.array(tr.history[-1][1:])
                current = np.array([(d['box'][0]+d['box'][2])/2,d['box'][3]])
                dt = timestamp-tr.last_seen
                allowed = max(80., float(np.linalg.norm(tr.velocity))*dt*3 + tr.radius*3)
                if np.linalg.norm(current-previous)>allowed:
                    tr.history.clear(); tr.smoothed_history.clear(); tr.ready=False; tr.velocity=np.zeros(2)
            tr.box, tr.confidence, tr.last_seen = d['box'], d['confidence'], timestamp
            x1,y1,x2,y2 = tr.box
            # Bottom-center works better for ground-plane actors in oblique views.
            tr.history.append((timestamp, (x1+x2)/2, y2))
            while len(tr.history)>2 and timestamp-tr.history[0][0]>HISTORY_SECONDS:
                tr.history.popleft()
            tr.position = np.array([(x1+x2)/2,y2], dtype=float)
            tr.ready = len(tr.history)>=MIN_OBSERVATIONS and timestamp-tr.history[0][0]>=MIN_HISTORY_SECONDS
            if tr.ready:
                tr.velocity, tr.position, tr.stability = estimate(tr.history)
            tr.smoothed_history.append((timestamp,*tr.position))
            while len(tr.smoothed_history)>2 and timestamp-tr.smoothed_history[0][0]>HISTORY_SECONDS:
                tr.smoothed_history.popleft()
            active[tid] = tr
        self.tracks = {k:v for k,v in self.tracks.items() if timestamp-v.last_seen <= 2.}
        return active
