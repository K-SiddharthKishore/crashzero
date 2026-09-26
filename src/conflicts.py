import itertools
import numpy as np
from config.settings import HORIZON, HIGH_RISK
from src.risk import interaction_score

def detect_conflicts(tracks):
    interactions = []
    ready = [t for t in tracks.values() if t.ready and t.stability >= .25]
    for a,b in itertools.combinations(ready,2):
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
        point = (a.project(t)+b.project(t))/2
        interactions.append({'ids':sorted([a.id,b.id]),'classes':[tracks[k].cls for k in sorted([a.id,b.id])],
            'risk':score,'ttc':round(t,3),'separation_px':round(sep,2),'radius_px':round(radius,2),
            'x':round(float(point[0]),2),'y':round(float(point[1]),2),'stability':round(stability,3),
            'convergence_px_s':round(convergence,2)})
    return sorted(interactions,key=lambda i:i['risk'],reverse=True)
