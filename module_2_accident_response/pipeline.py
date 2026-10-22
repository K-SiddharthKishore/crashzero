"""Independent upload/live analysis baseline.

YOLO supplies road-user observations; accident classification is a transparent
motion baseline, not an accident-trained temporal network.  Its outputs are
therefore explicitly marked experimental.
"""
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
import math
import os
import uuid
import cv2
import numpy as np
import torch

from .config import Module2Config
from .temporal import load_temporal_model, score_rgb_frames

ROAD={0:'person',1:'bicycle',2:'car',3:'motorcycle',5:'bus',7:'truck'}

class Module2Analyzer:
    def __init__(self, config=None): self.config=config or Module2Config.load()
    def _model(self):
        if not self.config.model_path.exists() and os.environ.get('CRASHZERO_V2_HOSTED') == '1':
            from src.model_assets import ensure_model
            ensure_model()
        if not self.config.model_path.exists(): raise RuntimeError('Module 2 YOLO weights are unavailable; no analysis was performed.')
        from ultralytics import YOLO
        return YOLO(str(self.config.model_path))
    @staticmethod
    def _center(box): return ((box[0]+box[2])/2,(box[1]+box[3])/2)
    def analyze_file(self,path,camera_id='UPLOAD',location='Location not configured',progress=None):
        path=Path(path); cap=cv2.VideoCapture(str(path))
        if not cap.isOpened(): raise ValueError('Unable to decode this video. Use a supported MP4, MOV, or AVI file.')
        fps=cap.get(cv2.CAP_PROP_FPS) or 30.; total=max(1,int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        model=self._model(); histories=defaultdict(lambda:deque(maxlen=18)); candidate=None; frame_index=0; last_frame=None
        temporal_device='mps' if torch.backends.mps.is_available() else 'cpu'
        temporal_model,temporal_threshold=load_temporal_model(self.config.temporal_model_path,temporal_device)
        if temporal_model is not None and fps<4:
            cap.release()
            raise ValueError('The trained temporal model requires video at 4 FPS or higher; analysis was withheld.')
        sampled=deque(maxlen=16);next_sample=0.;last_score_time=-1.;recent_scores=deque(maxlen=3);max_score=0.
        analysis_model=('YOLO tracking + trained temporal crash classifier' if temporal_model is not None
                        else 'YOLO tracking + experimental motion baseline')
        # ByteTrack is owned by this invocation through Ultralytics, never Module 1's tracker.
        for result in model.track(source=str(path),stream=True,persist=True,tracker='bytetrack.yaml',classes=list(ROAD),verbose=False):
            frame_index+=1; last_frame=result.orig_img; now=(frame_index-1)/fps
            boxes=result.boxes
            active_ids=[]
            if boxes is not None and boxes.id is not None:
                ids=boxes.id.int().cpu().tolist(); xyxy=boxes.xyxy.cpu().tolist(); conf=boxes.conf.cpu().tolist(); classes=boxes.cls.int().cpu().tolist()
                active_ids=ids
                for tid,b,c,klass in zip(ids,xyxy,conf,classes): histories[tid].append((now,self._center(b),float(c),ROAD.get(klass,'unknown'),b))
            if temporal_model is not None:
                if now+1e-6>=next_sample:
                    rgb=cv2.cvtColor(cv2.resize(result.orig_img,(160,96)),cv2.COLOR_BGR2RGB)
                    sampled.append(rgb);next_sample+=.25
                if len(sampled)==16 and now-last_score_time>=1.0:
                    score=score_rgb_frames(temporal_model,list(sampled),temporal_device)
                    max_score=max(max_score,score);last_score_time=now
                    event_offset=max(0.,now-1.875)
                    recent_scores.append({'score':score,'timestamp':event_offset,'track_ids':active_ids})
                    # Temporal evidence must persist across overlapping windows;
                    # a single noisy frame/window cannot trigger an incident.
                    if candidate is None and sum(x['score']>=temporal_threshold for x in recent_scores)>=2:
                        best=max((x for x in recent_scores if x['score']>=temporal_threshold),key=lambda x:x['score'])
                        candidate={'timestamp':best['timestamp'],'track_ids':best['track_ids'],'score':best['score'],
                                   'threshold':temporal_threshold,'temporal':True,'window_seconds':4.0}
            elif candidate is None:
                candidate=self._candidate(histories,now)
            if progress and frame_index%10==0: progress(min(.99,frame_index/total))
            if candidate and now>=candidate['timestamp']+self.config.post_event_seconds: break
        cap.release()
        if progress:progress(1.0)
        if not candidate:
            reason=(f'Temporal model score did not meet the calibrated threshold ({temporal_threshold:.3f}); no incident or call was created.'
                    if temporal_model is not None else 'No sufficiently supported motion candidate was found.')
            return None,{'frames':frame_index,'reason':reason,'model':analysis_model,
                         'temporal_threshold':temporal_threshold,'maximum_temporal_score':max_score}
        incident=self._make_incident(candidate,path,camera_id,location,fps)
        reason=('Temporal classifier exceeded its validation-selected threshold in multiple overlapping windows. Review the evidence; this model is not India-deployment validated.'
                if candidate.get('temporal') else 'Candidate passed motion evidence only; crash-specific classifier training is not yet available.')
        return incident,{'frames':frame_index,'reason':reason,'model':analysis_model,
                         'temporal_threshold':temporal_threshold,'maximum_temporal_score':max_score}
    def _candidate(self,histories,now):
        active=[(tid,list(h)) for tid,h in histories.items() if len(h)>=self.config.minimum_track_observations and now-h[-1][0]<.4]
        for i,(first_id,a) in enumerate(active):
            ax=np.array(a[-1][1]); av=(ax-np.array(a[-5][1]))/max(.001,a[-1][0]-a[-5][0])
            for second_id,b in active[i+1:]:
                bx=np.array(b[-1][1]); bv=(bx-np.array(b[-5][1]))/max(.001,b[-1][0]-b[-5][0])
                distance=float(np.linalg.norm(ax-bx)); closing=float(np.dot(av-bv,(bx-ax)/(distance+1e-6)))
                # Requires convergence plus spatial proximity; overlap alone is insufficient.
                if distance<110 and closing>45:
                    score=min(.86,.45+closing/220+(110-distance)/300)
                    if score>=self.config.likely_threshold:return {'timestamp':now,'track_ids':[first_id,second_id],'score':score,'distance':distance,'closing':closing}
        return None
    def _make_incident(self,candidate,source,camera_id,location,fps):
        stamp=datetime.now(timezone.utc).strftime('%Y%m%d')
        incident_id=f'CZ-AR-{stamp}-{uuid.uuid4().hex[:6].upper()}'
        clip,screenshot=self._extract(source,candidate['timestamp'],incident_id,fps)
        if candidate.get('temporal'):
            explanation=(f"A trained temporal video classifier scored {candidate['score']:.3f} across a 4-second window "
                         f"around {candidate['timestamp']:.1f}s (validation threshold {candidate['threshold']:.3f}). "
                         'This is an experimental candidate, not a confirmed crash.')
            reliability={'tracking':'supporting only','camera_motion':'not assessed','temporal_classifier':'ACCIDENT research benchmark; not Indian-deployment validated','geometry':'image-space only'}
        else:
            explanation=f'Experimental motion evidence: tracks {candidate["track_ids"]} converged (closing {candidate["closing"]:.1f} px/s) within {candidate["distance"]:.0f} px. This is a likely candidate, not a confirmed crash.'
            reliability={'tracking':'limited','camera_motion':'not assessed','temporal_classifier':'unavailable','geometry':'image-space only'}
        return {'incident_id':incident_id,'source_kind':'uploaded video','event_offset':candidate['timestamp'],'camera_id':camera_id,'location':location,
                'state':'LIKELY_ACCIDENT','score':candidate['score'],'track_ids':candidate['track_ids'],'clip_path':str(clip),'screenshot_path':str(screenshot),
                'original_recording_time':None,'reliability':reliability,'explanation':explanation,
                'temporal_model':bool(candidate.get('temporal'))}
    def _extract(self,source,event,incident_id,fps):
        start=max(0,event-self.config.pre_event_seconds); end=event+self.config.post_event_seconds
        cap=cv2.VideoCapture(str(source)); cap.set(cv2.CAP_PROP_POS_MSEC,start*1000)
        width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); safe_fps=max(1,min(30,fps))
        clip=self.config.evidence_dir/(incident_id+'.mp4'); writer=cv2.VideoWriter(str(clip),cv2.VideoWriter_fourcc(*'mp4v'),safe_fps,(width,height)); screenshot=self.config.evidence_dir/(incident_id+'.jpg')
        index=0
        while cap.get(cv2.CAP_PROP_POS_MSEC)/1000<=end:
            ok,frame=cap.read()
            if not ok:break
            writer.write(frame); index+=1
            if not screenshot.exists() and cap.get(cv2.CAP_PROP_POS_MSEC)/1000>=event:cv2.imwrite(str(screenshot),frame)
        writer.release();cap.release()
        if not screenshot.exists() and clip.exists():
            fallback=np.zeros((max(1,height),max(1,width),3),np.uint8);cv2.imwrite(str(screenshot),fallback)
        return clip,screenshot
