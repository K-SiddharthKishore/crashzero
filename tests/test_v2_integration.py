import time
from pathlib import Path
import cv2
import numpy as np
from config.settings import ROOT
from src.live import AnalysisWorker
from src.video.source import Camera, VideoFileSource
from src.video.simulation import FixtureDetector
from src.incidents.manager import IncidentStore, EvidenceBuffer
from src.video_processor import probe

def test_full_synthetic_collision_evidence(tmp_path,monkeypatch):
    path=ROOT/'data/simulations/collision.mp4'
    store=IncidentStore(tmp_path/'incidents')
    worker=AnalysisWorker(VideoFileSource(path),Camera(),detector=FixtureDetector(path.with_suffix('.json')),
        store=store,source_kind='SYNTHETIC TEST',realtime=False,output_dir=tmp_path/'analysis').start()
    worker.thread.join(timeout=30)
    assert not worker.thread.is_alive()
    assert worker.get()['status']=='COMPLETED',worker.get().get('message')
    records=store.list(); assert len(records)==1
    r=records[0]
    assert r['analysis_id']==worker.analysis_id
    assert r['source_id']==worker.source_id
    assert r['source_name']=='collision.mp4'
    assert r['alert_status']=='DEMO ALERT CREATED'
    assert r['source_kind']=='SYNTHETIC TEST'
    assert r['observed_at'] is None  # file offsets must not pretend to be capture wall clock
    assert Path(r['screenshot_path']).exists() and Path(r['before_path']).exists() and Path(r['after_path']).exists()
    assert probe(r['video_clip_path'])['frames']>=90
    assert r['timestamp']-r['clip_start']>=4.8 and r['clip_end']-r['timestamp']>=4.9
    assert not r['post_event_truncated']
    assert len(IncidentStore(tmp_path/'incidents').list())==1
    from streamlit.testing.v1 import AppTest
    import src.incidents.manager as module
    monkeypatch.setattr(module,'IncidentStore',lambda:store)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    demo=next(s for s in app.selectbox if s.label=='Offline scenario')
    demo.set_value('Collision · SYNTHETIC TEST').run()
    app.session_state['worker']=worker
    app.session_state['analysis_by_source']={worker.source_id:worker.analysis_id}
    app.radio[0].set_value('Incidents').run()
    assert not app.exception
    assert any('LIKELY COLLISION' in e.label for e in app.expander)
    app.radio[0].set_value('Live Analysis').run()
    assert next(s for s in app.selectbox if s.label=='Offline scenario').value=='Collision · SYNTHETIC TEST'
    next(s for s in app.selectbox if s.label=='Offline scenario').set_value('Normal · SYNTHETIC TEST').run()
    assert not app.exception
    assert not any('LIKELY COLLISION' in e.value for e in app.error)
    app.radio[0].set_value('Incidents').run()
    assert not any('LIKELY COLLISION' in e.label for e in app.expander)
    assert any('Start analysis' in e.value for e in app.info)
    # Finish a normal run in the same store: the collision must remain hidden.
    normal_path=ROOT/'data/simulations/normal.mp4'
    normal=AnalysisWorker(VideoFileSource(normal_path),Camera(),detector=FixtureDetector(normal_path.with_suffix('.json')),
        store=store,realtime=False,output_dir=tmp_path/'normal').start()
    normal.thread.join(30)
    assert normal.get()['status']=='COMPLETED'
    app.session_state['worker']=normal
    app.session_state['analysis_by_source']={worker.source_id:worker.analysis_id,normal.source_id:normal.analysis_id}
    app.run()
    assert not app.exception
    assert any('No likely accidents recorded for this analysis' in e.value for e in app.info)
    assert not any('LIKELY COLLISION' in e.label for e in app.expander)
    # History remains available explicitly, and changing back restores the right result.
    app.segmented_control[0].set_value('All saved incidents').run()
    assert any('LIKELY COLLISION' in e.label for e in app.expander)
    app.radio[0].set_value('Live Analysis').run()
    next(s for s in app.selectbox if s.label=='Offline scenario').set_value('Collision · SYNTHETIC TEST').run()
    app.radio[0].set_value('Incidents').run()
    assert not app.exception
    assert any('LIKELY COLLISION' in e.label for e in app.expander)

def test_corrupt_source_clean_failure(tmp_path):
    path=tmp_path/'bad.mp4';path.write_bytes(b'bad')
    worker=AnalysisWorker(VideoFileSource(path),Camera(),detector=object(),store=IncidentStore(tmp_path/'incidents')).start()
    worker.thread.join(timeout=5)
    assert worker.get()['status']=='ERROR'
    assert 'Traceback' not in worker.get()['message']

def test_truncated_clip_and_empty_frame_buffer(tmp_path):
    store=IncidentStore(tmp_path/'incidents'); buffer=EvidenceBuffer(Camera(),store)
    frame=np.zeros((240,320,3),np.uint8)
    for k in range(10):buffer.add(k/10,frame)
    buffer.trigger({'timestamp':.5,'state':'LIKELY COLLISION','track_ids':[1,2],
                    'road_users':['car','car'],'evidence_score':.9,'evidence_signals':{}})
    buffer.close()
    r=store.list()[0]
    assert r['pre_event_truncated'] and r['post_event_truncated']
    assert Path(r['video_clip_path']).exists()

def test_live_latest_frame_queue_and_release(monkeypatch):
    from src.video.source import WebcamSource
    class Capture:
        def __init__(self,*args):self.index=0;self.released=False
        def isOpened(self):return True
        def get(self,key):return 30
        def read(self):
            time.sleep(.005);self.index+=1
            return True,np.full((8,8,3),self.index%255,np.uint8)
        def release(self):self.released=True
    capture=Capture();monkeypatch.setattr(cv2,'VideoCapture',lambda *args:capture)
    source=WebcamSource().open();time.sleep(.035)
    t,frame=source.read()
    assert frame[0,0,0]>=3  # latest, not first: bounded queue dropped stale capture frames
    assert source.latest.qsize()<=1
    source.close();assert capture.released and not source.reader.is_alive()

def test_stop_releases_file_source(tmp_path):
    path=ROOT/'data/simulations/normal.mp4';source=VideoFileSource(path)
    worker=AnalysisWorker(source,Camera(),detector=FixtureDetector(path.with_suffix('.json')),
        store=IncidentStore(tmp_path/'incidents'),output_dir=tmp_path/'analysis').start()
    deadline=time.monotonic()+5
    while worker.get()['frame'] is None and worker.thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
    worker.stop();worker.thread.join(timeout=5)
    assert not worker.thread.is_alive() and not source.capture.isOpened()
    assert worker.get()['status']=='STOPPED'

def test_stream_rejects_unsupported_scheme():
    import pytest
    from src.video.source import StreamSource
    with pytest.raises(ValueError):StreamSource('file:///tmp/secret')
