"""Explicit synthetic detection fixtures. Never presented as detector output."""
import json
from pathlib import Path
import numpy as np

SCENARIOS = ['normal','perspective_overlap','near_miss','collision','legal_turn','normal_stop','single_bike']

def scene(name,t):
    # Units are pixels on a 960x540 synthetic canvas, not real road measurements.
    if name=='collision':
        x=170+60*min(t,5)
        actors=[(1,'car',x,290),(2,'car',790-60*min(t,5),290)]
    elif name=='near_miss':
        actors=[(1,'car',170+60*t,280),(2,'motorcycle',790-60*t,300+min(90,120*max(0,t-4.5)))]
    elif name=='perspective_overlap':
        actors=[(1,'car',120+45*t,280),(2,'bus',130+45*t,284)]
    elif name=='normal_stop': actors=[(1,'car',170+60*min(t,5),290)]
    elif name in ('legal_turn','single_bike'):
        progress=min(t,5.35) if name=='single_bike' else t
        actors=[(1,'motorcycle',170+60*min(progress,5),230+80*max(0,progress-5))]
    else: actors=[(1,'car',100+50*t,280),(2,'bus',200+50*t,340)]
    return [{'id':i,'class':kind,'box':[x-22,y-32,x+22,y],'confidence':.95} for i,kind,x,y in actors]

class FixtureDetector:
    def __init__(self,path):
        metadata=json.loads(Path(path).read_text())
        if metadata.get('kind')!='SYNTHETIC_DETECTION_FIXTURE': raise ValueError('Not a synthetic fixture')
        self.frames=metadata['detections']; self.index=0
    def track(self,frame):
        result=self.frames[min(self.index,len(self.frames)-1)];self.index+=1;return result
