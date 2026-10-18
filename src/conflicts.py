import itertools
import numpy as np
from config.settings import HORIZON, HIGH_RISK
from src.risk import interaction_score

def spatial_pairs(tracks):
    """Sweep projected image envelopes before expensive pair calculations."""
    envelopes=[]
    for tr in tracks:
        end=tr.project(HORIZON);pad=tr.radius*1.4
        low=np.minimum(tr.position,end)-pad;high=np.maximum(tr.position,end)+pad
        envelopes.append((float(low[0]),float(high[0]),float(low[1]),float(high[1]),tr))
    active=[]
    for left,right,top,bottom,tr in sorted(envelopes,key=lambda e:e[0]):
        active=[item for item in active if item[0]>=left]
        for other_right,other_top,other_bottom,other in active:
            if top<=other_bottom and bottom>=other_top: yield other,tr
        active.append((right,top,bottom,tr))


def detect_conflicts(tracks):
    interactions = []
    ready = [t for t in tracks.values() if t.ready and t.stability >= .25]
    for a,b in spatial_pairs(ready):
        delta = b.position-a.position
        relative = b.velocity-a.velocity
        v2 = float(relative@relative)
        distance = float(np.linalg.norm(delta))
        radius = a.radius+b.radius
        if v2 < 9 or distance > np.sqrt(v2)*HORIZON+radius*1.4:
            continue
        dot = float(delta@relative)
        if dot >= 0: continue  # separating or parallel, not a future convergence
        t = float(np.clip(-dot/v2,0,HORIZON))
        sep = float(np.linalg.norm(delta+relative*t))
        convergence = -dot/max(distance,1.)
        if t < .08 or sep > radius*1.4 or distance-sep < radius*.2:
            continue
        stability = min(a.stability,b.stability) * min(1.,min(a.confidence,b.confidence)/.6)
        score = interaction_score(t,sep,radius,convergence,stability,a.cls in ('person','bicycle','motorcycle') or b.cls in ('person','bicycle','motorcycle'))
        road={}
        if all(tr.road_position is not None and tr.road_velocity is not None and tr.road_radius is not None for tr in (a,b)):
            road_delta=np.asarray(b.road_position)-a.road_position
            road_relative=np.asarray(b.road_velocity)-a.road_velocity
            road_v2=float(road_relative@road_relative)
            road_t=float(np.clip(-road_delta@road_relative/road_v2,0,HORIZON)) if road_v2>1e-10 else 0.
            road_sep=float(np.linalg.norm(road_delta+road_relative*road_t))
            road={'separation_road_units':road_sep,'road_ttc':road_t,'road_proximity':road_sep<=(a.road_radius+b.road_radius)*1.4}
            if not road['road_proximity']: continue
        point = (a.project(t)+b.project(t))/2
        interactions.append({'ids':sorted([a.id,b.id]),'classes':[tracks[k].cls for k in sorted([a.id,b.id])],
            'risk':score,'ttc':round(t,3),'separation_px':round(sep,2),'radius_px':round(radius,2),
            'x':round(float(point[0]),2),'y':round(float(point[1]),2),'stability':round(stability,3),
            'convergence_px_s':round(convergence,2),**road})
    return sorted(interactions,key=lambda i:i['risk'],reverse=True)
