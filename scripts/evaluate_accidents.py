"""Run real YOLO/ByteTrack and temporal verification against a labelled manifest."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hashlib
import json
import time
import cv2
from src.detector import RoadDetector
from src.trajectory import TrajectoryStore
from src.conflicts import detect_conflicts
from src.safety.verifier import CrashVerifier
from src.video.camera_motion import CameraMotionGuard
from src.evaluation import summarize
from src.alerts.service import engine_fingerprint


def evaluate(manifest, device='cpu', seconds_limit=None):
    data=json.loads(Path(manifest).read_text());rows=[];frames=0;started=time.monotonic()
    # One manifest scope; never pool external benchmark and deployment cameras.
    scope=data['scope'];camera_splits={}
    for clip in data['clips']:
        if not clip.get('label_source') or not clip.get('license'): raise ValueError('Label provenance and licence required.')
        split=clip.get('split','test');camera=clip['camera_id']
        if camera in camera_splits and camera_splits[camera]!=split: raise ValueError('Camera leakage across splits.')
        camera_splits[camera]=split
    for clip in data['clips']:
        if clip.get('split','test')!='test': continue
        path=Path(clip['path'])
        if not path.is_absolute(): path=Path(manifest).resolve().parent/path
        with path.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=clip['sha256']: raise ValueError('Media checksum mismatch.')
        detector=RoadDetector(device);tracks=TrajectoryStore();verifier=CrashVerifier();guard=CameraMotionGuard()
        cap=cv2.VideoCapture(str(path));fps=cap.get(cv2.CAP_PROP_FPS)
        if not cap.isOpened() or not fps>0: raise ValueError('Video unavailable.')
        stride=max(1,int(__import__('math').ceil(fps/12)));index=0;last=0.;candidates=0;camera_unsafe=0
        while True:
            ok,frame=cap.read()
            if not ok: break
            t=index/fps;index+=1
            if seconds_limit and t>=seconds_limit: break
            last=t
            if (index-1)%stride: continue
            width=min(960,frame.shape[1]);height=round(frame.shape[0]*width/frame.shape[1])
            frame=cv2.resize(frame,(width,height))
            detections=detector.track(frame);active=tracks.update(detections,t)
            motion=guard.update(frame,t,[d['box'] for d in detections])
            camera_unsafe+=not motion['available'] or motion['moving']
            verifier.update(active,detect_conflicts(active),t,camera_motion=motion)
            candidates+=len(verifier.candidates);frames+=1
        cap.release();verifier.flush(last)
        events=clip['events']
        if seconds_limit: events=[e for e in events if e['end']<=last]
        predictions=[e for e in verifier.results if e['phase']=='LIKELY_ACCIDENT']
        rows.append({'id':clip['id'],'camera_id':clip['camera_id'],'sha256':digest,'duration_seconds':last+1/fps,
            'events':events,'predictions':predictions,'candidate_observations':candidates,
            'unsafe_camera_observations':camera_unsafe,'final_states':[e['phase'] for e in verifier.results]})
    report=summarize(rows,scope)
    elapsed=time.monotonic()-started
    report.update(engine_fingerprint=engine_fingerprint(),device=device,processed_frames=frames,
        elapsed_seconds=elapsed,processed_fps=frames/elapsed,rows=rows,
        real_auto_test_approved=False,reviewed_by=None,
        call_false_positives=None,call_gate_evaluation='Not measured: complete evidence and reviewed deployment labels required.')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('manifest');parser.add_argument('--device',default='cpu',choices=['cpu','mps'])
    parser.add_argument('--output',default='outputs/evaluation/real-report.json');parser.add_argument('--limit-seconds',type=float)
    args=parser.parse_args();report=evaluate(args.manifest,args.device,args.limit_seconds)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
