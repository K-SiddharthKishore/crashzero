import json
import cv2
import numpy as np
import pytest
from config.settings import ROOT
from src.video_processor import probe, process_video
from src.historical import load_history, grid_hotspots
from src.prediction import load_or_train, timeline

@pytest.mark.parametrize('content',[b'',b'not an mp4 video'])
def test_invalid_video(tmp_path,content):
    p=tmp_path/'invalid.mp4';p.write_bytes(content)
    with pytest.raises(ValueError,match='No readable'):probe(p)

def test_no_detection_video_and_exports(tmp_path):
    p=tmp_path/'blank.mp4';v=cv2.VideoWriter(str(p),cv2.VideoWriter_fourcc(*'mp4v'),10,(320,240))
    for _ in range(10):v.write(np.zeros((240,320,3),dtype=np.uint8))
    v.release()
    class EmptyDetector:
        def track(self,frame):return []
    out=tmp_path/'blank_result'
    s=process_video(p,out,max_seconds=1,detector=EmptyDetector())
    assert s['road_users']==s['near_misses']==s['live_risk']==0
    assert probe(out/'processed.mp4')['frames']==10
    assert (out/'events.csv').read_text().count('\n')==1
    assert json.loads((out/'analytics.json').read_text())['events']==[]

def test_real_history_and_model():
    d=load_history()
    assert len(d)>80000 and d.collision_id.is_unique
    assert str(d.date.min().date())=='2024-01-01'
    g=grid_hotspots(d);assert g.crashes.sum()==d.geo_valid.sum()
    model,metrics=load_or_train(d)
    assert metrics['train_rows']+metrics['test_rows']==len(d)
    a=timeline(model,'BROOKLYN',0,'SEDAN');b=timeline(model,'BROOKLYN',0,'SEDAN')
    assert a.equals(b) and a.score.between(0,100).all() and len(a)==24
    assert 'injury' not in metrics['features']

def test_real_demo_assets():
    s=json.loads((ROOT/'outputs/demo/analytics.json').read_text())
    assert s['road_users']>0 and s['frames_analyzed']>10
    assert (ROOT/'outputs/demo/tracks.csv').stat().st_size>100
    assert probe(ROOT/'outputs/demo_processed.mp4')['frames']>10
