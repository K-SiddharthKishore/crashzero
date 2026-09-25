"""Analytic fixtures only: synthetic test trajectories are never demo records."""
from collections import deque
import numpy as np
import pytest
from src.trajectory import Track, TrajectoryStore
from src.conflicts import detect_conflicts
from src.events import EventManager
from src.fusion import fuse
from src.risk import interaction_score
from src.hotspots import emerging_status
from config.settings import category

def track(i,p,v,cls='car'):
    tr=Track(i,cls,[p[0]-5,p[1]-10,p[0]+5,p[1]],.9,0.)
    tr.position=np.array(p,dtype=float);tr.velocity=np.array(v,dtype=float);tr.ready=True;tr.stability=1
    return tr

def test_same_time_convergence():
    a=track(1,(0,0),(50,0));b=track(2,(100,0),(-50,0))
    i=detect_conflicts({1:a,2:b})[0]
    assert i['ttc']==pytest.approx(1.)
    assert i['separation_px']==0
    assert i['risk']>=61

def test_crossing_lines_different_times_are_safe():
    a=track(1,(0,0),(50,0));b=track(2,(50,100),(0,-20))
    assert detect_conflicts({1:a,2:b})==[]

def test_parallel_and_diverging():
    assert detect_conflicts({1:track(1,(0,0),(10,0)),2:track(2,(20,0),(10,0))})==[]
    assert detect_conflicts({1:track(1,(0,0),(-10,0)),2:track(2,(20,0),(10,0))})==[]

def test_motion_uses_seconds_and_resets_after_gap():
    store=TrajectoryStore()
    for k in range(12):
        t=k/10; d={'id':1,'class':'car','box':[t*20,0,t*20+10,10],'confidence':.9}
        active=store.update([d],t)
    assert active[1].velocity[0]==pytest.approx(20)
    assert active[1].project(2)[0]-active[1].position[0]==pytest.approx(40)
    active=store.update([d],3)
    assert not active[1].ready
    assert not store.update([],6)
    assert not store.tracks

def conflict():return {'ids':[1,2],'classes':['car','car'],'risk':88,'ttc':1.2,'x':50.,'y':20.}

def test_near_miss_dedup_and_separation():
    e=EventManager(); tr={1:track(1,(0,0),(-10,0)),2:track(2,(100,0),(10,0))}
    for t in [0,.1,.2]:e.update([conflict()],tr,t)
    e.update([],tr,.3);e.update([],tr,.9)
    assert len(e.events)==1 and e.events[0]['status']=='prototype near miss'
    e.update([conflict()],tr,1.0)
    assert not e.active

def test_lost_tracks_are_not_near_misses():
    e=EventManager();e.update([conflict()],{},0);e.update([],{},1.1)
    assert e.events[0]['status']=='unresolved / track lost'

def test_overlap_never_confirms_collision_or_near_miss():
    e=EventManager();tr={1:track(1,(0,0),(1,0)),2:track(2,(1,0),(1,0))}
    e.update([conflict()],tr,0)
    tr={1:track(1,(0,0),(-10,0)),2:track(2,(100,0),(10,0))}
    e.update([],tr,.2);e.update([],tr,.8)
    assert e.events[0]['status']=='overlap / review'

def test_bounds_and_thresholds():
    assert [category(x) for x in [0,30,31,60,61,80,81,100]]==['LOW','LOW','MODERATE','MODERATE','HIGH','HIGH','CRITICAL','CRITICAL']
    for t in [0,1,2.5,10]:
        assert 0<=interaction_score(t,0,20,100,1,True)<=100

def test_fusion_missing_source_and_zero_weights():
    assert fuse(live=70)['score']==70
    assert fuse()['score'] is None
    assert fuse(80,40,100,{'historical':1,'predictive':1,'live':2})['score']==80
    assert fuse(10,20,30,{'historical':0,'predictive':0,'live':0})['score'] is None

def test_unknown_history_cannot_create_emerging_hotspot():
    s={'high_interactions':5,'timeline':[{'high_pairs':0}]*5+[{'high_pairs':3}]*5}
    assert emerging_status(s)['status']=='Live conflict cluster'
    assert emerging_status(s,10,True)['status']=='Emerging hotspot candidate'
