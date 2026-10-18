"""Measured pipeline speed on real traffic, not an accuracy evaluation."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json,time,math,statistics,resource
import cv2
import torch
from config.settings import ROOT
from src.detector import RoadDetector
from src.trajectory import TrajectoryStore
from src.conflicts import detect_conflicts
from src.safety.verifier import CrashVerifier
from src.video.camera_motion import CameraMotionGuard

rows=[]
for device in ['cpu']+(['mps'] if torch.backends.mps.is_available() else []):
    for name in ('traffic','highway','mixed_traffic'):
        cap=cv2.VideoCapture(str(ROOT/f'data/demo/{name}.mp4'));fps=cap.get(cv2.CAP_PROP_FPS);frames=[]
        for i in range(int(fps*8)):
            ok,frame=cap.read()
            if not ok: break
            if i%max(1,math.ceil(fps/12)):continue
            w=min(960,frame.shape[1]);h=round(frame.shape[0]*w/frame.shape[1]);frames.append((i/fps,cv2.resize(frame,(w,h))))
        cap.release()
        detector=RoadDetector(device);detector.model.predict(frames[0][1],device=device,verbose=False)
        tracks=TrajectoryStore();verifier=CrashVerifier();guard=CameraMotionGuard();latencies=[];unsafe=0;count=0
        started=time.monotonic()
        for t,frame in frames:
            then=time.monotonic();detections=detector.track(frame);active=tracks.update(detections,t)
            motion=guard.update(frame,t,[d['box'] for d in detections]);unsafe+=not motion['available'] or motion['moving']
            verifier.update(active,detect_conflicts(active),t,camera_motion=motion)
            count+=len(detections);latencies.append(time.monotonic()-then)
        elapsed=time.monotonic()-started
        row={'device':device,'video':name,'frames':len(frames),'fps':round(len(frames)/elapsed,2),
            'median_frame_ms':round(statistics.median(latencies)*1000,1),'p95_frame_ms':round(sorted(latencies)[int(len(latencies)*.95)]*1000,1),
            'camera_guard_unsafe_frames':unsafe,'detections':count,'likely_events':sum(e['phase']=='LIKELY_ACCIDENT' for e in verifier.results)}
        rows.append(row);print(json.dumps(row),flush=True)
report={'scope':'Performance only; eight seconds per real demo, after model warmup. No accident ground truth. Includes detection/tracking, motion, camera guard and verifier; excludes UI and evidence encoding.',
    'rows':rows,'peak_process_memory_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
out=ROOT/'outputs/evaluation/pipeline_benchmark.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2))
