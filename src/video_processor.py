"""Bounded, offline video pipeline with auditable exports and browser-safe H.264."""
import csv, hashlib, json, math, sqlite3, subprocess, time
from pathlib import Path
import cv2
import numpy as np
from config.settings import ROOT, HIGH_RISK, CRITICAL_RISK
from src.detector import RoadDetector
from src.trajectory import TrajectoryStore
from src.conflicts import detect_conflicts
from src.events import EventManager
from src.visualization import draw, heatmap

EVENT_COLUMNS=['event_id','timestamp','end_time','object_ids','classes','peak_risk','min_ttc','x','y','severity','status']

def probe(path):
    cap=cv2.VideoCapture(str(path))
    try:
        ok,frame=cap.read()
        fps=float(cap.get(cv2.CAP_PROP_FPS))
        if not cap.isOpened() or not ok or frame is None:
            raise ValueError('No readable video frames. Choose a valid MP4, MOV or AVI file.')
        if not math.isfinite(fps) or fps<=0 or fps>240:
            raise ValueError('Video FPS metadata is missing or unsupported; re-encode at a known frame rate.')
        return {'fps':fps,'frames':int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), 'width':frame.shape[1],'height':frame.shape[0]}
    finally: cap.release()

def save_events(out,session_id,events):
    with (out/'events.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=EVENT_COLUMNS); writer.writeheader(); writer.writerows(events)
    db=sqlite3.connect(ROOT/'outputs/events.sqlite')
    try:
        db.execute('CREATE TABLE IF NOT EXISTS events (session_id TEXT, event_id TEXT, status TEXT, timestamp REAL, peak_risk INTEGER, payload TEXT, PRIMARY KEY(session_id,event_id))')
        db.execute('DELETE FROM events WHERE session_id=?',(session_id,))
        db.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)',[(session_id,e['event_id'],e['status'],e['timestamp'],e['peak_risk'],json.dumps(e)) for e in events]); db.commit()
    finally: db.close()

def process_video(path,out,device='cpu',max_seconds=60,target_fps=12,progress=None,detector=None):
    path=Path(path); out=Path(out); meta=probe(path)
    out.mkdir(parents=True,exist_ok=True)
    detector=detector if detector is not None else RoadDetector(device)
    stride=max(1,math.ceil(meta['fps']/target_fps)); fps=meta['fps']/stride
    width=min(960,meta['width']); width-=width%2
    height=round(meta['height']*width/meta['width']); height-=height%2
    cap=cv2.VideoCapture(str(path)); writer=cv2.VideoWriter(str(out/'annotated_raw.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),fps,(width,height))
    if not writer.isOpened():
        cap.release(); raise RuntimeError('Could not open the video encoder.')
    store=TrajectoryStore(); manager=EventManager(); seen=set(); timeline=[]; counts={}; peak=0
    start=time.perf_counter(); idx=0; processed=0; first=None; peakframe=None; last_t=0
    limit=int(max_seconds*meta['fps']); total=min(limit,meta['frames']) if meta['frames']>0 else limit
    trackfile=(out/'tracks.csv').open('w',newline=''); tw=csv.writer(trackfile)
    tw.writerow(['frame','timestamp','track_id','class','x','y','x1','y1','x2','y2','vx_px_s','vy_px_s','stability','risk'])
    try:
        while idx<limit:
            ok,frame=cap.read()
            if not ok: break
            frame_idx=idx; idx+=1
            if frame_idx%stride: continue
            t=frame_idx/meta['fps']; last_t=t
            frame=cv2.resize(frame,(width,height))
            if first is None: first=frame.copy()
            detections=detector.track(frame); active=store.update(detections,t)
            seen.update(active)
            for tr in active.values(): counts[tr.id]=tr.cls
            interactions=detect_conflicts(active); manager.update(interactions,active,t)
            risk=max([i['risk'] for i in interactions],default=0)
            timeline.append({'timestamp':round(t,3),'risk':risk,'active_tracks':len(active),'high_pairs':sum(i['risk']>=HIGH_RISK for i in interactions)})
            for tr in active.values():
                trisk=max([i['risk'] for i in interactions if tr.id in i['ids']],default=0)
                tw.writerow([frame_idx,round(t,3),tr.id,tr.cls,*tr.position,*tr.box,*tr.velocity,tr.stability,trisk])
            annotated=draw(frame,active,interactions,t,sum(e['status']=='prototype near miss' for e in manager.events))
            writer.write(annotated); processed+=1
            if peakframe is None or risk>peak:
                peakframe=annotated.copy(); peak=risk
            if progress and processed%10==0: progress(min(idx/max(total,1),.99),processed,risk)
    finally:
        cap.release(); writer.release(); trackfile.close()
    if not processed: raise ValueError('The video did not produce readable frames.')
    manager.flush(last_t)
    elapsed=time.perf_counter()-start
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-y','-i',str(out/'annotated_raw.mp4'),'-an','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'processed.mp4')],check=True,timeout=120)
    (out/'annotated_raw.mp4').unlink()
    cv2.imwrite(str(out/'preview.jpg'),peakframe); cv2.imwrite(str(out/'heatmap.jpg'),heatmap(first,manager.events))
    session_id=hashlib.sha256(path.read_bytes()).hexdigest()[:12]+'-'+out.name
    events=manager.events
    from collections import Counter
    types=Counter(' ↔ '.join(sorted(e['classes'])) for e in events)
    near=[e for e in events if e['status']=='prototype near miss']
    summary={'session_id':session_id,'source_file':path.name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'device':device,'duration':round(processed/fps,2),'source_fps':meta['fps'],'analysis_fps':round(fps,2),
        'frames_analyzed':processed,'width':width,'height':height,'inference_seconds':round(elapsed,2),'throughput_fps':round(processed/elapsed,2),
        'road_users':len(seen),'class_counts':dict(Counter(counts.values())), 'peak_risk':peak,
        'live_risk':round(float(np.percentile([r['risk'] for r in timeline],90)),1),
        'current_risk':timeline[-1]['risk'],'high_interactions':len(events),
        'critical_interactions':sum(e['peak_risk']>=CRITICAL_RISK for e in events),
        'near_misses':len(near),'conflict_types':dict(types),'events':events,'timeline':timeline,
        'truncated':meta['frames']>limit,'pipeline_version':'1.0',
        'risk_definition':'Live clip index = 90th percentile of frame maximum pair risk; peak and last-frame scores shown separately.',
        'geography':'Unverified camera location; not linked to NYC history',
        'evidence':'REAL VIDEO • Algorithmic, unvalidated image-space conflict indicators'}
    save_events(out,session_id,events)
    (out/'analytics.json').write_text(json.dumps(summary,indent=2))
    if progress: progress(1.,processed,summary['current_risk'])
    return summary
