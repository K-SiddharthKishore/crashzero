"""Local SQLite incident records, timestamped JPEG ring and browser-playable clips."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import sqlite3
import subprocess
import uuid
import cv2
import numpy as np
from config.settings import ROOT
from config.v2 import SAFETY

class DemoAlertService:
    def create(self, incident):
        return {'status':'DEMO ALERT CREATED', 'mode':'SIMULATED — no external dispatch',
                'incident_id':incident['incident_id'], 'created_at':datetime.now(timezone.utc).isoformat()}

class IncidentStore:
    def __init__(self, root=None):
        self.root = Path(root or ROOT/'outputs/incidents'); self.root.mkdir(parents=True,exist_ok=True)
        self.db = self.root/'incidents.sqlite'
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, created_at TEXT, payload TEXT)')
    def save(self, record):
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT OR REPLACE INTO incidents VALUES (?,?,?)',
                (record['incident_id'],record['created_at'],json.dumps(record)))
    def list(self):
        with sqlite3.connect(self.db) as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM incidents ORDER BY created_at DESC LIMIT 200')]

class EvidenceBuffer:
    def __init__(self, camera, store=None, config=SAFETY, source_kind='video', started_at=None):
        self.cfg = config; self.camera = camera; self.store = store or IncidentStore()
        self.frames = deque(); self.pending = []; self.last_t = -1.
        self.source_kind = source_kind; self.started_at = started_at or datetime.now(timezone.utc)
        self.encoder = ThreadPoolExecutor(max_workers=1,thread_name_prefix='CrashZero-evidence')
        self.exports = []
    def add(self,t,frame):
        if t-self.last_t < 1/self.cfg.buffer_fps-.001: return
        ok,jpg = cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,78])
        if not ok: return
        entry = (t,jpg.tobytes()); self.last_t=t; self.frames.append(entry)
        # Retain enough history for verification latency as well as pre-event footage.
        while self.frames and t-self.frames[0][0] > self.cfg.before_seconds+self.cfg.verification_seconds+1:
            self.frames.popleft()
        for pending in self.pending:
            if t > pending['frames'][-1][0]: pending['frames'].append(entry)
        for pending in list(self.pending):
            if t >= pending['record']['timestamp']+self.cfg.after_seconds: self._finish(pending,False)
    def trigger(self,event):
        if not self.frames: return
        incident_id = 'CZ-'+uuid.uuid4().hex[:10].upper()
        folder = self.store.root/incident_id; folder.mkdir()
        frames = [f for f in self.frames if f[0]>=event['timestamp']-self.cfg.before_seconds]
        if not frames: frames=list(self.frames)[-1:]
        event_frame = min(frames,key=lambda f:abs(f[0]-event['timestamp']))
        (folder/'event.jpg').write_bytes(event_frame[1]); (folder/'before.jpg').write_bytes(frames[0][1])
        now=datetime.now(timezone.utc).isoformat()
        record = {**event, **self.camera.metadata(), 'incident_id':incident_id, 'created_at':now,
            'event_type':event['state'], 'verification_status':event['state'],
            'camera_name':self.camera.name, 'registered_location':self.camera.location,
            'source_kind':self.source_kind, 'time_basis':'source offset in seconds' if self.source_kind!='live camera' else 'capture clock',
            'observed_at':(self.started_at+timedelta(seconds=event['timestamp'])).isoformat() if self.source_kind=='live camera' else None,
            'screenshot_path':str(folder/'event.jpg'),'before_path':str(folder/'before.jpg'),
            'video_clip_path':None,'evidence_status':'CAPTURING AFTER EVENT'}
        record['alert'] = DemoAlertService().create(record); record['alert_status']=record['alert']['status']
        self.store.save(record)
        self.pending.append({'record':record,'folder':folder,'frames':frames})
    def _finish(self,pending,truncated):
        self.pending.remove(pending)
        self.exports.append(self.encoder.submit(self._encode,pending,truncated))
    def _encode(self,pending,truncated):
        r,folder,frames = pending['record'],pending['folder'],pending['frames']
        (folder/'after.jpg').write_bytes(frames[-1][1]); r['after_path']=str(folder/'after.jpg')
        r['clip_start']=frames[0][0]; r['clip_end']=frames[-1][0]
        r['pre_event_truncated']=frames[0][0]>r['timestamp']-self.cfg.before_seconds+.2
        r['post_event_truncated']=truncated
        try:
            import imageio_ffmpeg
            frame=cv2.imdecode(np.frombuffer(frames[0][1],np.uint8),cv2.IMREAD_COLOR)
            h,w=frame.shape[:2]; raw=folder/'raw.mp4'
            writer=cv2.VideoWriter(str(raw),cv2.VideoWriter_fourcc(*'mp4v'),self.cfg.buffer_fps,(w,h))
            if not writer.isOpened(): raise RuntimeError('encoder unavailable')
            try:
                # Resample on source timestamps so irregular inference does not accelerate playback.
                index=0
                for t in np.arange(frames[0][0],frames[-1][0]+.05,1/self.cfg.buffer_fps):
                    while index+1<len(frames) and frames[index+1][0]<=t: index+=1
                    writer.write(cv2.imdecode(np.frombuffer(frames[index][1],np.uint8),cv2.IMREAD_COLOR))
            finally: writer.release()
            output=folder/'event.mp4'
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(raw),'-an','-c:v','libx264',
                '-pix_fmt','yuv420p','-movflags','+faststart',str(output)],check=True,timeout=30,capture_output=True)
            raw.unlink(); r['video_clip_path']=str(output); r['evidence_status']='EVIDENCE SAVED'
        except Exception:
            r['evidence_status']='SCREENSHOTS SAVED — CLIP ENCODING FAILED'
        self.store.save(r)
    def close(self):
        for pending in list(self.pending): self._finish(pending,True)
        self.encoder.shutdown(wait=True)
        for future in self.exports: future.result()
