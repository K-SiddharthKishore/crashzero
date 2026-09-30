import cv2
import numpy as np
import pytest
from src.safety.verifier import CrashVerifier, AccidentStateMachine
from src.trajectory import TrajectoryStore
from src.conflicts import detect_conflicts
from src.video.simulation import scene
from src.video.camera_motion import CameraMotionGuard
from src.calibration import RoadCalibration


def run_scenario(generator, motion=None, end=12):
    tracks=TrajectoryStore(); verifier=CrashVerifier(); results=[]; phases=[]
    for k in range(int(end*12)):
        t=k/12
        active=tracks.update(generator(t),t)
        results+=verifier.update(active,detect_conflicts(active),t,camera_motion=motion)
        phases += [e['phase'] for e in verifier.candidates.values()]
    verifier.flush(t)
    return list(verifier.results),phases


def test_state_machine_forbids_immediate_confirmation():
    e={}; AccidentStateMachine.transition(e,'CANDIDATE',0)
    with pytest.raises(ValueError): AccidentStateMachine.transition(e,'LIKELY_ACCIDENT',0)


def test_explicit_temporal_progression_and_groups():
    results,phases=run_scenario(lambda t:scene('collision',t))
    event=next(e for e in results if e['phase']=='LIKELY_ACCIDENT')
    assert 'CANDIDATE' in phases and 'VERIFYING' in phases
    assert [h['state'] for h in event['state_history']]==['MONITORING','CANDIDATE','VERIFYING','LIKELY_ACCIDENT']
    assert all(event['evidence_groups'].values())
    assert event['verified_at']-event['timestamp']>=2


def test_short_stream_is_uncertain():
    results,_=run_scenario(lambda t:scene('collision',t),end=6)
    assert results and all(e['phase']=='UNCERTAIN' for e in results)


@pytest.mark.parametrize('motion',[{'available':True,'moving':True},{'available':False,'moving':False}])
def test_camera_motion_or_unmeasurable_background_withholds_accident(motion):
    results,_=run_scenario(lambda t:scene('collision',t),motion)
    assert results and all(e['phase']!='LIKELY_ACCIDENT' for e in results)


def stationary_collision(t):
    data=scene('collision',t)
    x=490+70*min(max(t-5,0),.4)
    data[1]['box']=[x-22,258,x+22,290]
    return data


def test_striking_a_stationary_vehicle():
    results,_=run_scenario(stationary_collision)
    likely=[e for e in results if e['phase']=='LIKELY_ACCIDENT']
    assert len(likely)==1,results
    assert likely[0]['evidence_signals']['stationary_target_displacement']


def test_congested_stop_go_and_overlap():
    def jam(t):
        x=3*np.sin(t)
        return [{'id':i,'class':'car','confidence':.95,'box':[50+i*20+x,50,85+i*20+x,90]} for i in range(12)]
    results,_=run_scenario(jam)
    assert not any(e['phase']=='LIKELY_ACCIDENT' for e in results)


def test_global_motion_is_measured():
    rng=np.random.default_rng(18)
    frame=rng.integers(0,255,(240,320,3),dtype=np.uint8)
    guard=CameraMotionGuard()
    guard.update(frame,0)
    still=guard.update(frame,.1)
    shifted=cv2.warpAffine(frame,np.float32([[1,0,7],[0,1,3]]),(320,240))
    moving=guard.update(shifted,.2)
    assert still['available'] and not still['moving']
    assert moving['available'] and moving['moving'] and moving['displacement_px']>5
    assert guard.update(shifted,.3)['moving']


def test_calibration_projection_and_corridors():
    c=RoadCalibration({'image_points':[[0,0],[100,0],[100,100],[0,100]],
        'road_points':[[0,0],[1,0],[1,1],[0,1]],
        'corridors':[{'movement':'LEFT TURN','polygon':[[0,0],[100,0],[100,100],[0,100]]}]})
    assert c.project((50,50))==pytest.approx([.5,.5])
    assert c.corridor((50,50))=='LEFT TURN'
    with pytest.raises(ValueError): RoadCalibration({'image_points':[[0,0]]*4,'road_points':[[0,0]]*4})
    assert RoadCalibration({}).project((50,50)) is None
