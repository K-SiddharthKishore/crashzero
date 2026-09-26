"""One background inference worker per source. UI polls immutable snapshots."""
import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
import time
import uuid
import cv2
from config.settings import ROOT, HIGH_RISK
from config.v2 import SAFETY
from src.detector import RoadDetector
from src.trajectory import TrajectoryStore
from src.conflicts import detect_conflicts
from src.events import EventManager
from src.safety.verifier import CrashVerifier
from src.incidents.manager import EvidenceBuffer
from src.visualization import draw, heatmap

class AnalysisWorker:
    def __init__(self,source,camera,device='cpu',detector=None,store=None,source_kind='video',realtime=True,output_dir=None):
        self.source=source; self.camera=camera; self.device=device; self.detector=detector
        self.incident_store=store; self.source_kind=source_kind; self.realtime=realtime
        self.stop_event=threading.Event(); self.lock=threading.Lock()
        self.snapshot={'status':'STARTING','frame':None,'events':[],'candidates':[],'results':[],
                       'risk':0,'road_users':0,'conflicts':0,'near_misses':0,'fps':0.,'timestamp':0.}
        self.thread=None; self.last_poll=time.monotonic()
        self.out=Path(output_dir) if output_dir is not None else ROOT/'outputs/live'/uuid.uuid4().hex[:12]
    def start(self):
        self.thread=threading.Thread(target=self._run,daemon=True,name='CrashZero-analysis'); self.thread.start(); return self
    def stop(self): self.stop_event.set()
    def get(self):
        self.last_poll=time.monotonic()
        with self.lock: return copy.deepcopy(self.snapshot)
    def _publish(self,**values):
        with self.lock: self.snapshot.update(values)
    def _run(self):
        evidence=None; manager=EventManager(); verifier=CrashVerifier(); tracks=TrajectoryStore()
        t=0.; first=None; processed=0; start=time.monotonic()
        try:
            self.source.open()
            detector=self.detector if self.detector is not None else RoadDetector(self.device)
            self.out.mkdir(parents=True,exist_ok=True)
            evidence=EvidenceBuffer(self.camera,self.incident_store,source_kind=self.source_kind)
            stride=1 if self.source.live else max(1,math.ceil(self.source.fps/12))
            index=0; start=time.monotonic()
            while not self.stop_event.is_set():
                # Release devices if the browser disconnects instead of recording indefinitely.
                if time.monotonic()-self.last_poll>120: break
                item=self.source.read()
                if item is None:
                    if self.source.live: self._publish(status='DISCONNECTED',message='Camera stopped delivering frames. Stop and restart after checking the connection.')
                    break
                t,frame=item; index+=1
                if (index-1)%stride: continue
                width=min(960,frame.shape[1]); width-=width%2
                height=round(frame.shape[0]*width/frame.shape[1]); height-=height%2
                frame=cv2.resize(frame,(width,height))
                if first is None: first=frame.copy()
                detections=detector.track(frame)
                active=tracks.update(detections,t)
                interactions=detect_conflicts(active); manager.update(interactions,active,t)
                verified=verifier.update(active,interactions,t)
                near=sum(e['status']=='prototype near miss' for e in manager.events)
                visible={i:tr for i,tr in active.items() if tr.confidence>=SAFETY.minimum_confidence and len(tr.history)>=SAFETY.minimum_display_observations}
                annotated=draw(frame.copy(),visible,interactions,t,near)
                evidence.add(t,annotated)
                for event in verified:
                    if event['state'].startswith('LIKELY'): evidence.trigger(event)
                processed+=1
                self._publish(status='MONITORING',frame=cv2.cvtColor(annotated,cv2.COLOR_BGR2RGB),
                    risk=max([i['risk'] for i in interactions],default=0),road_users=len(visible),
                    conflicts=len(manager.active),near_misses=near,events=copy.deepcopy(manager.events),
                    candidates=copy.deepcopy(list(verifier.candidates.values())),results=list(verifier.results),
                    timestamp=t,fps=processed/max(time.monotonic()-start,.01),
                    camera=self.camera.metadata(),source_kind=self.source_kind)
                if self.realtime and not self.source.live:
                    self.stop_event.wait(max(0,t-(time.monotonic()-start)))
            manager.flush(t); verifier.flush(t)
            if processed==0: raise ValueError('No readable frames. Choose another video or check camera access.')
            self._publish(events=copy.deepcopy(manager.events),results=list(verifier.results),candidates=[],conflicts=0,
                near_misses=sum(e['status']=='prototype near miss' for e in manager.events))
        except Exception as exc:
            self._publish(error_code=type(exc).__name__)
            # Never display exception strings: stream backends may include credential-bearing URLs.
            self._publish(status='ERROR',message='Analysis could not continue. Check the video, local model, device permissions or stream connection. See README troubleshooting.')
        finally:
            self.source.close()
            if evidence:
                try: evidence.close()
                except Exception:
                    self._publish(status='ERROR',message='Evidence could not be finalized. Check free disk space; saved incident records remain available.')
            if first is not None:
                self.out.mkdir(parents=True,exist_ok=True)
                cv2.imwrite(str(self.out/'heatmap.jpg'),heatmap(first,manager.events))
                (self.out/'events.json').write_text(json.dumps({'camera':self.camera.metadata(),
                    'source_kind':self.source_kind,'events':manager.events},indent=2))
                self._publish(heatmap=str(self.out/'heatmap.jpg'),out=str(self.out))
            if self.snapshot['status'] not in ('ERROR','DISCONNECTED'):
                self._publish(status='STOPPED' if self.stop_event.is_set() else 'COMPLETED')
