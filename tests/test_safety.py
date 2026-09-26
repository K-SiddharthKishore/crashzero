"""Analytic scenario tests are not a labeled real-world accuracy evaluation."""
import numpy as np
import pytest
from src.trajectory import TrajectoryStore
from src.conflicts import detect_conflicts
from src.safety.verifier import CrashVerifier
from src.video.simulation import scene

def replay(name,drop=False):
    store=TrajectoryStore(); verifier=CrashVerifier(); results=[]; candidates=0
    for k in range(144):
        t=k/12
        detections=[] if drop and t>5.4 else scene(name,t)
        tracks=store.update(detections,t)
        results.extend(verifier.update(tracks,detect_conflicts(tracks),t)); candidates+=len(verifier.candidates)
    return results,candidates

@pytest.mark.parametrize('scenario',['normal','perspective_overlap','near_miss','legal_turn','normal_stop'])
def test_no_false_likely_accident(scenario):
    results,_=replay(scenario)
    assert not any(r['state'].startswith('LIKELY') for r in results)

def test_collision_temporal_and_deduplicated():
    results,candidates=replay('collision')
    likely=[r for r in results if r['state']=='LIKELY COLLISION']
    assert candidates>0 and len(likely)==1,results
    e=likely[0]
    assert e['verified_at']-e['timestamp']>=2
    assert e['evidence_signals']['simultaneous_motion_change']==1
    assert e['evidence_signals']['post_event_stop']==1

def test_single_bike_requires_turn_deceleration_and_stop():
    results,candidates=replay('single_bike')
    assert candidates>0 and len([r for r in results if r['state']=='LIKELY SINGLE-VEHICLE ACCIDENT'])==1,results

def test_disappearance_never_confirms_collision():
    results,_=replay('collision',drop=True)
    assert not any(r['state'].startswith('LIKELY') for r in results)

def test_impossible_jump_resets_track():
    store=TrajectoryStore()
    for k in range(15):tracks=store.update(scene('normal',k/12),k/12)
    d=scene('normal',2);d[0]['box']=[800,400,830,430]
    tracks=store.update(d,1.3)
    assert not tracks[1].ready

def test_near_miss_fixture_records_observed_separation():
    from src.events import EventManager
    store=TrajectoryStore();manager=EventManager()
    for k in range(144):
        t=k/12;tracks=store.update(scene('near_miss',t),t)
        manager.update(detect_conflicts(tracks),tracks,t)
    manager.flush(t)
    assert len(manager.events)==1
    assert manager.events[0]['status']=='prototype near miss'
