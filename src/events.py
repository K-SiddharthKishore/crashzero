"""Deduplicated conflict episodes; near misses require observed separation."""
from config.settings import HIGH_RISK, RESOLVE_SECONDS, COOLDOWN_SECONDS, category
import numpy as np

def overlaps(a,b):
    x1,y1,x2,y2=a.box; u1,v1,u2,v2=b.box
    return min(x2,u2)>max(x1,u1) and min(y2,v2)>max(y1,v1)

class EventManager:
    def __init__(self):
        self.active={}; self.events=[]; self.cooldowns={}; self.counter=0
    def finish(self,key,status,t):
        state=self.active.pop(key)
        event=state['event']; event['status']=status; event['end_time']=round(t,3)
        event['severity']=category(event['peak_risk'])
        self.events.append(event); self.cooldowns[key]=t+COOLDOWN_SECONDS
    def update(self,interactions,tracks,t):
        high={tuple(i['ids']):i for i in interactions if i['risk']>=HIGH_RISK}
        for key,i in high.items():
            if key not in self.active and t>=self.cooldowns.get(key,-1):
                self.counter+=1
                self.active[key]={'event':{'event_id':f'CZ-{self.counter:04d}','timestamp':round(t,3),
                    'object_ids':i['ids'],'classes':i['classes'],'peak_risk':i['risk'],'min_ttc':i['ttc'],
                    'x':i['x'],'y':i['y']},'last_high':t,'overlap':False,'separate_since':None}
            if key in self.active:
                s=self.active[key]; e=s['event']; s['last_high']=t
                if i['risk']>e['peak_risk']: e.update(peak_risk=i['risk'],x=i['x'],y=i['y'])
                e['min_ttc']=min(e['min_ttc'],i['ttc'])
        for key,s in list(self.active.items()):
            a,b=(tracks.get(k) for k in key)
            if a is not None and b is not None:
                s['overlap'] |= overlaps(a,b)
                delta=b.position-a.position
                separating=float(delta@(b.velocity-a.velocity))>0
                clear=np.linalg.norm(delta)>(a.radius+b.radius)*1.5
                if key not in high and separating and clear:
                    if s['separate_since'] is None: s['separate_since']=t
                    if t-s['separate_since']>=RESOLVE_SECONDS:
                        self.finish(key,'overlap / review' if s['overlap'] else 'prototype near miss',t)
                else: s['separate_since']=None
            elif t-s['last_high']>1.0:
                self.finish(key,'unresolved / track lost',t)
        self.cooldowns={k:v for k,v in self.cooldowns.items() if v>=t}
    def flush(self,t):
        for key in list(self.active): self.finish(key,'unresolved / clip ended',t)
