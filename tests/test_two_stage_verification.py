import json
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from test_lab.candidates import group_candidates
from test_lab.evidence import capture_pair
from test_lab.storage import TestHistory
from test_lab.verification import PROMPT, verify_pair, settings, safe_failure
from module_2_accident_response.storage import AccidentRepository
from module_2_accident_response.pipeline import Module2Analyzer


def _video(path, frames=40, fps=10):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), fps, (32, 24))
    for index in range(frames):
        writer.write(np.full((24, 32, 3), index, dtype=np.uint8))
    writer.release()


def _run(path, event_id='event-1'):
    return {'test_id': event_id.split('-event')[0] if '-event' in event_id else 'run-1',
            'source_name': 'video.mp4', 'source_path': str(path), 'source_sha256': 'a'*64,
            'result': 'Uncertain', 'event_timestamp': 1., 'model_score': .5,
            'threshold': .7, 'suspicion_threshold': .4, 'duration_seconds': 4.,
            'windows_analyzed': 2, 'evidence_paths': [], 'decision_basis': 'test',
            'model_name': 'mock', 'events': [{'event_id': event_id, 'timestamp': 1.,
                'score': .5, 'reason': 'Temporal accident prediction crossed the suspicion threshold',
                'original_detected': False, 'evidence_paths': [str(path),str(path)],
                'frame_timestamps': [1.,2.], 'evidence_limitation': None}]}


def test_candidates_group_adjacent_scores_and_preserve_separate_events():
    scores = [{'timestamp': t, 'score': s} for t,s in
              [(2.,.5),(3.,.8),(4.,.75),(9.,.55),(10.,.4)]]
    groups = group_candidates(scores, .7, .4, cooldown=3.)
    assert len(groups) == 2
    assert groups[0]['original_detected'] is True
    assert groups[1]['original_detected'] is False
    assert groups[0]['timestamp'] == 2.
    assert groups[0]['peak_timestamp'] == 3.


def test_quiet_gap_does_not_hide_later_vulnerable_road_user_event():
    # An early false alarm at 3s previously swallowed a collision signal at 6s
    # because both were within the three-second cooldown.
    scores = [{'timestamp': t, 'score': s} for t, s in
              [(3., .91), (4., .42), (5., .39), (6., .85), (7., .66),
               (8., .61), (9., .80)]]
    groups = group_candidates(scores, .72, .45, cooldown=3.)
    assert [group['timestamp'] for group in groups] == [3., 6.]


def test_prompt_accepts_strong_aftermath_without_forcing_close_traffic_positive():
    assert 'strong visible crash aftermath' in PROMPT
    assert 'Do not require the exact impact frame' in PROMPT
    assert 'Close spacing' in PROMPT
    assert 'Return UNCERTAIN' in PROMPT


def test_evidence_uses_fps_and_final_frame_when_video_ends(tmp_path):
    source = tmp_path/'source.mp4'
    _video(source)
    paths, times, limitation = capture_pair(source, tmp_path/'pair', 1.2)
    assert len(paths) == 2 and times == pytest.approx([1.2,2.2])
    assert limitation is None
    _, times, limitation = capture_pair(source, tmp_path/'ending', 3.6)
    assert times == pytest.approx([3.6,3.9]) and limitation


def test_openai_mock_gets_only_two_images_in_one_request(tmp_path):
    image = tmp_path/'image.jpg'
    cv2.imwrite(str(image), np.zeros((24,32,3), np.uint8))
    calls = []
    class MockResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text=json.dumps({
                'classification':'UNCERTAIN', 'explanation':'Two frames are insufficient.',
                'visible_evidence':[], 'limitations':['Motion between frames is not visible.']}),
                usage=SimpleNamespace(input_tokens=100,output_tokens=40))
    result = verify_pair([image,image], 'mock-vision',
                         client=SimpleNamespace(responses=MockResponses()))
    assert result['classification'] == 'UNCERTAIN' and len(calls) == 1
    content = calls[0]['input'][0]['content']
    assert sum(item['type'] == 'input_image' for item in content) == 2
    assert calls[0]['max_output_tokens'] == 1200
    with pytest.raises(ValueError, match='Exactly two'):
        verify_pair([image], 'mock-vision', client=SimpleNamespace(responses=MockResponses()))


def test_failed_json_has_safe_diagnostic():
    error = json.JSONDecodeError('unfinished', '{', 1)
    assert safe_failure(error) == 'OpenAI returned incomplete or invalid JSON.'


def test_history_caches_and_enforces_budget_without_api_call(tmp_path):
    history = TestHistory(tmp_path/'history.sqlite3')
    source = tmp_path/'video.mp4'
    source.write_bytes(b'fake')
    history.save(_run(source))
    config = settings() | {'model':'mock', 'budget_usd':.1, 'max_requests_per_video':1}
    assert history.claim_verification('event-1', config) == 'claimed'
    history.finish_verification('event-1', {'classification':'LIKELY_ACCIDENT',
        'explanation':'Visible damage.', 'visible_evidence':['damaged vehicle'],
        'limitations':[], 'input_tokens':100,'output_tokens':20}, config)
    assert history.claim_verification('event-1', config) == 'already_done'
    second = _run(source, 'run-2-event-1')
    history.save(second)
    assert history.claim_verification('run-2-event-1', config) == 'cached'
    assert history.event('run-2-event-1')['classification'] == 'LIKELY_ACCIDENT'
    assert history.event('run-2-event-1')['attempt_count'] == 0
    third = _run(source, 'run-3-event-1')
    third['source_sha256'] = 'b'*64
    history.save(third)
    assert history.claim_verification('run-3-event-1', config | {'budget_usd':0.}) == 'budget_exhausted'
    assert history.event('run-3-event-1')['status'] == 'VERIFICATION_FAILED'


def test_module2_stores_pair_and_reuses_verification(tmp_path):
    repo=AccidentRepository(tmp_path/'module2.sqlite3')
    incident={'incident_id':'CZ-AR-ONE','source_kind':'uploaded video',
        'state':'POSSIBLE_ACCIDENT','score':.5,'explanation':'suspected',
        'reliability':{},'track_ids':[],'source_key':'same-video',
        'evidence_paths':['a.jpg','b.jpg'],'frame_timestamps':[1.,2.]}
    repo.save_incident(incident)
    config=settings() | {'model':'mock','budget_usd':.1}
    assert repo.claim_verification('CZ-AR-ONE',config)=='claimed'
    repo.finish_verification('CZ-AR-ONE',{'classification':'UNCERTAIN',
        'explanation':'Not enough evidence.','visible_evidence':[],
        'limitations':['Only two frames.'],'input_tokens':100,'output_tokens':20},config)
    assert repo.verification('CZ-AR-ONE')['classification']=='UNCERTAIN'
    repo.save_incident(incident | {'incident_id':'CZ-AR-TWO'})
    assert repo.claim_verification('CZ-AR-TWO',config)=='cached'
    assert repo.verification('CZ-AR-TWO')['attempt_count']==0


def test_module2_overlap_without_closing_motion_is_not_candidate(tmp_path):
    from module_2_accident_response.config import Module2Config
    analyzer=Module2Analyzer(Module2Config.load(tmp_path))
    histories={1:[(t,(20.,20.),.9,'car',[0,0,40,40]) for t in np.arange(0,.6,.1)],
               2:[(t,(21.,20.),.9,'car',[1,0,41,40]) for t in np.arange(0,.6,.1)]}
    assert analyzer._candidate(histories,.5) is None


def test_module2_incident_keeps_clip_and_two_frame_evidence(tmp_path):
    from module_2_accident_response.config import Module2Config
    source=tmp_path/'video.mp4'
    _video(source)
    analyzer=Module2Analyzer(Module2Config.load(tmp_path))
    incident=analyzer._make_incident({'timestamp':1.2,'track_ids':[1],
        'score':.5,'high_sensitivity':True,
        'trigger_reason':'Sudden tracked vehicle deceleration'},
        source,'CAM','test location',10.)
    assert incident['state']=='POSSIBLE_ACCIDENT'
    assert len(incident['evidence_paths'])==2
    assert incident['frame_timestamps']==pytest.approx([1.2,2.2])
    assert (analyzer.config.evidence_dir/f"{incident['incident_id']}.mp4").exists()
