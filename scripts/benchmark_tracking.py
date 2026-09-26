"""Same-frame tracking diagnostics; ID counts are not ground-truth ID-switch metrics."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collections import Counter
import json,time,math
import cv2
from src.detector import RoadDetector
from config.settings import ROOT

def main():
    cap=cv2.VideoCapture(str(ROOT/'data/demo/traffic.mp4'));fps=cap.get(cv2.CAP_PROP_FPS)
    frames=[]
    for k in range(int(fps*8)):
        ok,f=cap.read()
        if not ok:break
        if k%max(1,math.ceil(fps/12))==0:
            w=min(960,f.shape[1]);h=round(f.shape[0]*w/f.shape[1]);frames.append(cv2.resize(f,(w,h)))
    cap.release();report={}
    for name,tracker,conf in [('v1','bytetrack.yaml',.20),('v2',str(ROOT/'config/bytetrack-v2.yaml'),.10)]:
        detector=RoadDetector(tracker=tracker,confidence=conf)
        detector.model.predict(frames[0],imgsz=640,device='cpu',verbose=False)
        counts=Counter();started=time.monotonic()
        for frame in frames:
            detections=detector.track(frame)
            for d in detections:counts[d['id']]+=1
        preview=frames[-1].copy()
        for d in detections:
            a,b,c,e=map(int,d['box']);cv2.rectangle(preview,(a,b),(c,e),(120,230,150),2)
            cv2.putText(preview,f"{d['class']} #{d['id']}",(a,max(15,b)),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1)
        cv2.imwrite(str(ROOT/'outputs'/f'tracking_{name}.jpg'),preview)
        report[name]={'frames':len(frames),'unique_ids':len(counts),'ids_seen_less_than_3_frames':sum(n<3 for n in counts.values()),
            'median_observations_per_id':sorted(counts.values())[len(counts)//2] if counts else 0,
            'fps':round(len(frames)/(time.monotonic()-started),2)}
    report['scope']='Eight seconds of traffic.mp4 at the application analysis rate, CPU after warmup; no labeled identities, so no ID-switch or accuracy claim.'
    path=ROOT/'outputs/tracking_benchmark.json';path.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
