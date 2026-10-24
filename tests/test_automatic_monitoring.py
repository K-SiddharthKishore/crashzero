import json
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from module_2_accident_response.config import Module2Config
from module_2_accident_response.monitor import AutomaticMonitor
from module_2_accident_response.pipeline import Module2Analyzer, evidence_timestamp
from test_lab.automatic import (SessionBudget, _effective_budget_root, alert_state,
                                run_automatic_verification)
from test_lab.storage import TestHistory


class FakeSource:
    live = True
    source = 0
    def __init__(self, times):
        self.times = iter(times)
        self.closed = False
    def open(self):
        return self
    def read(self):
        try:
            t = next(self.times)
            return t, np.full((32, 48, 3), int(t) % 255, np.uint8)
        except StopIteration:
            return None
    def close(self):
        self.closed = True


class FakeModel:
    def track(self, *_args, **_kwargs):
        return [SimpleNamespace(boxes=None)]


def test_hosted_visitors_share_one_spending_cap(tmp_path, monkeypatch):
    monkeypatch.setenv('CRASHZERO_V2_HOSTED', '1')
    monkeypatch.setenv('CRASHZERO_SHARED_BUDGET_DIR', str(tmp_path / 'shared'))
    first = SessionBudget(_effective_budget_root(tmp_path / 'visitor-a'))
    second = SessionBudget(_effective_budget_root(tmp_path / 'visitor-b'))
    config = {'estimated_input_tokens': 100_000, 'estimated_output_tokens': 1_200,
              'input_rate': .20, 'output_rate': 1.25, 'budget_usd': .03}
    assert first.path == second.path
    assert first.reserve('visitor-a:event-1', config)
    assert not second.reserve('visitor-b:event-1', config)
    assert second.spent() > 0


@pytest.mark.parametrize('event_times,expected', [([], 0), ([1.0], 1),
                                                  ([1.0, 6.0], 2), ([1.0, 13.0], 2)])
def test_live_monitor_continues_and_stores_two_frames(tmp_path, monkeypatch, event_times, expected):
    config = Module2Config.load(root=tmp_path, data_dir=tmp_path/'module2_accident_response')
    times = [round(i/10, 1) for i in range(160)]
    source = FakeSource(times)
    calls = []
    def candidate(_self, _histories, now):
        if any(abs(now-t) < .01 for t in event_times):
            return {'timestamp': now, 'track_ids': [1], 'score': .8,
                    'trigger_reason': 'Mock grouped event'}
        return None
    monkeypatch.setattr(Module2Analyzer, '_candidate', candidate)
    def verifier(repo, identity, **_kwargs):
        calls.append(identity)
        assert len(repo.verification(identity)['evidence_paths']) == 2
    monitor = AutomaticMonitor(config, source, model=FakeModel(), temporal=(None, .7),
                               verifier=verifier)
    monitor.run()
    assert monitor.status == 'COMPLETED' and source.closed
    assert len(calls) == expected
    assert monitor.snapshot()['state'] == ('NO SUSPICIOUS EVENT DETECTED' if not calls else 'ANALYZING')
    for identity in calls:
        record = monitor.repo.verification(identity)
        assert record['frame_timestamps'][1] - record['frame_timestamps'][0] == pytest.approx(1., abs=.11)
        assert all(cv2.imread(path) is not None for path in record['evidence_paths'])
    assert monitor.repo.calls() == []


def test_converging_motion_evidence_waits_for_estimated_encounter(tmp_path, monkeypatch):
    config = Module2Config.load(root=tmp_path, data_dir=tmp_path/'module2_accident_response')
    signal = {'timestamp': .5, 'distance': 100., 'closing': 80., 'score': .8,
              'track_ids': [1, 2],
              'trigger_reason': 'Close interaction with converging tracked motion'}
    assert evidence_timestamp(signal) == pytest.approx(1.75)
    monkeypatch.setattr(Module2Analyzer, '_candidate',
                        lambda _self, _histories, now: signal if now == .5 else None)
    seen = []
    def verifier(repo, identity, **_kwargs):
        seen.append(repo.verification(identity)['frame_timestamps'])
    monitor = AutomaticMonitor(config, FakeSource([round(i/10, 1) for i in range(35)]),
                               model=FakeModel(), temporal=(None, .7), verifier=verifier)
    monitor.run()
    assert len(seen) == 1
    assert seen[0][0] == pytest.approx(1.8, abs=.11)
    assert seen[0][1] == pytest.approx(2.8, abs=.11)


@pytest.mark.parametrize('classification,expected,note', [
    ('LIKELY_ACCIDENT', 'ALERT', False),
    ('NO_ACCIDENT_EVIDENCE', 'NO ALERT', False),
    ('UNCERTAIN', 'REVIEW', True),
])
def test_automatic_verification_result_and_no_duplicate_charge(tmp_path, monkeypatch,
                                                                classification, expected, note):
    monkeypatch.setenv('OPENAI_SESSION_BUDGET_USD', '.50')
    monkeypatch.setenv('OPENAI_MAX_REQUESTS_PER_VIDEO', '3')
    image = tmp_path/'frame.jpg'
    cv2.imwrite(str(image), np.zeros((24, 32, 3), np.uint8))
    history = TestHistory(tmp_path/'history.sqlite3')
    history.save({'test_id':'run', 'source_name':'sample.mp4', 'source_path':'sample.mp4',
                  'source_sha256':'a'*64, 'result':'Uncertain', 'event_timestamp':1.,
                  'model_score':.5, 'threshold':.7, 'suspicion_threshold':.4,
                  'duration_seconds':3., 'windows_analyzed':2, 'evidence_paths':[],
                  'decision_basis':'test', 'model_name':'mock', 'events':[{ 'event_id':'event',
                  'timestamp':1., 'score':.5, 'reason':'Grouped temporal candidate',
                  'original_detected':False, 'evidence_paths':[str(image),str(image)],
                  'frame_timestamps':[1.,2.], 'evidence_limitation':None}]})
    calls = []
    class Responses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(status='completed', output_text=json.dumps({
                'classification':classification, 'explanation':'Mocked.',
                'visible_evidence':[], 'limitations':[]}),
                usage=SimpleNamespace(input_tokens=100, output_tokens=20))
    client = SimpleNamespace(responses=Responses())
    first = run_automatic_verification(history, 'event', kind='test',
                                        budget_root=tmp_path, client=client)
    second = run_automatic_verification(history, 'event', kind='test',
                                         budget_root=tmp_path, client=client)
    assert len(calls) == 1
    assert sum(item['type']=='input_image' for item in calls[0]['input'][0]['content']) == 2
    assert first['status'] == second['status'] == 'VERIFIED'
    state, status = alert_state([second])
    assert state == expected and bool(status) is note
    assert SessionBudget(tmp_path).spent() > 0
    audit = (tmp_path/'verification_audit.jsonl').read_text()
    assert json.loads(audit.splitlines()[-1])['classification'] == classification


def test_budget_failure_is_neutral(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_SESSION_BUDGET_USD', '0')
    image = tmp_path/'frame.jpg'
    cv2.imwrite(str(image), np.zeros((24, 32, 3), np.uint8))
    history = TestHistory(tmp_path/'history.sqlite3')
    history.save({'test_id':'run', 'source_name':'x', 'source_path':'x',
                  'source_sha256':'a'*64, 'result':'Uncertain', 'event_timestamp':1.,
                  'model_score':.5, 'threshold':.7, 'suspicion_threshold':.4,
                  'duration_seconds':3., 'windows_analyzed':2, 'evidence_paths':[],
                  'decision_basis':'test', 'model_name':'mock', 'events':[{ 'event_id':'event',
                  'timestamp':1., 'score':.5, 'reason':'Grouped candidate',
                  'original_detected':False, 'evidence_paths':[str(image),str(image)],
                  'frame_timestamps':[1.,2.], 'evidence_limitation':None}]})
    class Never:
        def create(self, **kwargs):
            pytest.fail('A paid request was made despite the zero budget')
    record = run_automatic_verification(history, 'event', kind='test', budget_root=tmp_path,
                                         client=SimpleNamespace(responses=Never()))
    assert record['status'] == 'VERIFICATION_FAILED'
    assert alert_state([record])[0] == 'VERIFICATION UNAVAILABLE'
    assert 'budget' in alert_state([record])[1].lower()


def test_api_failure_does_not_retry_or_claim_negative(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_SESSION_BUDGET_USD', '.50')
    image = tmp_path/'frame.jpg'
    cv2.imwrite(str(image), np.zeros((24, 32, 3), np.uint8))
    history = TestHistory(tmp_path/'history.sqlite3')
    history.save({'test_id':'run', 'source_name':'x', 'source_path':'x',
                  'source_sha256':'b'*64, 'result':'Uncertain', 'event_timestamp':1.,
                  'model_score':.5, 'threshold':.7, 'suspicion_threshold':.4,
                  'duration_seconds':3., 'windows_analyzed':2, 'evidence_paths':[],
                  'decision_basis':'test', 'model_name':'mock', 'events':[{ 'event_id':'event',
                  'timestamp':1., 'score':.5, 'reason':'Grouped candidate',
                  'original_detected':False, 'evidence_paths':[str(image),str(image)],
                  'frame_timestamps':[1.,2.], 'evidence_limitation':None}]})
    calls = []
    class Failing:
        def create(self, **kwargs):
            calls.append(kwargs)
            raise TimeoutError('simulated timeout')
    client = SimpleNamespace(responses=Failing())
    first = run_automatic_verification(history, 'event', kind='test', budget_root=tmp_path,
                                        client=client)
    second = run_automatic_verification(history, 'event', kind='test', budget_root=tmp_path,
                                         client=client)
    assert len(calls) == 1
    assert first['status'] == second['status'] == 'VERIFICATION_FAILED'
    assert alert_state([second]) == ('VERIFICATION UNAVAILABLE', 'Stage 2 verification unavailable.')


def test_uploaded_video_without_candidate_stays_neutral(tmp_path, monkeypatch):
    from src.video.source import VideoFileSource
    video = tmp_path/'normal.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), 10, (48, 32))
    for _ in range(30):
        writer.write(np.zeros((32, 48, 3), np.uint8))
    writer.release()
    config = Module2Config.load(root=tmp_path, data_dir=tmp_path/'module2_accident_response')
    monkeypatch.setattr(Module2Analyzer, '_candidate', lambda *_args: None)
    monitor = AutomaticMonitor(config, VideoFileSource(video), model=FakeModel(), temporal=(None, .7),
                               verifier=lambda *_args, **_kwargs: pytest.fail('Unexpected paid request'))
    monitor.run()
    assert monitor.status == 'COMPLETED'
    assert monitor.snapshot()['state'] == 'NO SUSPICIOUS EVENT DETECTED'
    assert monitor.repo.incidents() == []


def test_alert_state_requires_actual_verified_negative():
    negative = {'status': 'VERIFIED', 'classification': 'NO_ACCIDENT_EVIDENCE'}
    likely = {'status': 'VERIFIED', 'classification': 'LIKELY_ACCIDENT'}
    uncertain = {'status': 'VERIFIED', 'classification': 'UNCERTAIN'}
    pending = {'status': 'PENDING', 'classification': None}
    failed = {'status': 'VERIFICATION_FAILED', 'error': 'OpenAI API 503.'}
    assert alert_state([])[0] == 'NO SUSPICIOUS EVENT DETECTED'
    assert alert_state([], analyzing=True)[0] == 'ANALYZING'
    assert alert_state([pending])[0] == 'ANALYZING'
    assert alert_state([negative, pending])[0] == 'ANALYZING'
    assert alert_state([negative, negative])[0] == 'NO ALERT'
    assert alert_state([negative, uncertain])[0] == 'REVIEW'
    assert alert_state([negative, failed])[0] == 'VERIFICATION UNAVAILABLE'
    assert alert_state([likely, uncertain, failed])[0] == 'ALERT'


def test_live_monitor_status_follows_mock_openai_result(tmp_path, monkeypatch):
    config = Module2Config.load(root=tmp_path, data_dir=tmp_path/'module2_accident_response')
    monkeypatch.setattr(Module2Analyzer, '_candidate',
                        lambda _self, _histories, now: {'timestamp': now, 'track_ids': [1],
                        'score': .8, 'trigger_reason': 'Mock grouped event'} if now == 1.0 else None)
    def verifier(repo, identity, **_kwargs):
        repo.finish_verification(identity, {
            'classification': 'LIKELY_ACCIDENT', 'explanation': 'Visible collision.',
            'visible_evidence': [], 'limitations': [], 'input_tokens': 100,
            'output_tokens': 20}, __import__('test_lab.verification', fromlist=['settings']).settings())
    monitor = AutomaticMonitor(config, FakeSource([round(i/10, 1) for i in range(35)]),
                               model=FakeModel(), temporal=(None, .7), verifier=verifier)
    assert monitor.snapshot()['state'] == 'ANALYZING'
    monitor.run()
    assert monitor.snapshot()['state'] == 'ALERT'
    assert monitor.repo.calls() == []
