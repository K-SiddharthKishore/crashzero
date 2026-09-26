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

def test_full_synthetic_collision_evidence(tmp_path):
    path=ROOT/'data/simulations/collision.mp4'
    store=IncidentStore(tmp_path/'incidents')
    worker=AnalysisWorker(VideoFileSource(path),Camera(),detector=FixtureDetector(path.with_suffix('.json')),
        store=store,source_kind='SYNTHETIC TEST',realtime=False).start()
    worker.thread.join(timeout=30)
    assert not worker.thread.is_alive()
    assert worker.get()['status']=='COMPLETED',worker.get().get('message')
    records=store.list(); assert len(records)==1
    r=records[0]
    assert r['alert_status']=='DEMO ALERT CREATED'
    assert r['source_kind']=='SYNTHETIC TEST'
    assert r['observed_at'] is None  # file offsets must not pretend to be capture wall clock
    assert Path(r['screenshot_path']).exists() and Path(r['before_path']).exists() and Path(r['after_path']).exists()
    assert probe(r['video_clip_path'])['frames']>=90
    assert r['timestamp']-r['clip_start']>=4.8 and r['clip_end']-r['timestamp']>=4.9
    assert not r['post_event_truncated']
    assert len(IncidentStore(tmp_path/'incidents').list())==1

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
