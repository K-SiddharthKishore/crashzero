"""TEST alerts hand off to the phone only after a verified positive result."""
from pathlib import Path

from module_2_accident_response.alerts import CallService
from module_2_accident_response.storage import AccidentRepository
from test_lab.config import TestLabConfig as LabConfig
from test_lab.ui import UploadAnalysis
import test_lab.ui as test_ui


def test_verified_test_call_is_opt_in_and_deduplicated(tmp_path, monkeypatch):
    repo = AccidentRepository(tmp_path / 'module2.sqlite3')
    service = CallService(repo)
    digest = 'a' * 64
    monkeypatch.setenv('M2_TEST_ALERT_CALLS_ENABLED', 'false')
    assert service.submit_verified_test_alert(digest) is None
    for key, value in {
        'M2_TEST_ALERT_CALLS_ENABLED': 'true',
        'M2_CALL_MODE': 'real',
        'M2_CALL_PROVIDER': 'android_gateway',
        'M2_REAL_CALLS_ENABLED': 'true',
        'M2_CALL_KILL_SWITCH': 'false',
        'M2_APPROVED_TEST_PHONE': '+919999999999',
        'M2_TEST_PHONE_CONSENT': 'true',
        'M2_GATEWAY_TOKEN': 'x' * 32,
    }.items():
        monkeypatch.setenv(key, value)
    first = service.submit_verified_test_alert(digest)
    second = service.submit_verified_test_alert(digest)
    assert first['id'] == second['id']
    assert first['status'] == 'QUEUED'
    assert first['kind'] == 'verified_test'
    assert len(repo.calls()) == 1


def test_test_worker_dispatches_only_confirmed_accidents(tmp_path, monkeypatch):
    config = LabConfig.load(data_dir=tmp_path / 'test_lab')
    digest = 'b' * 64
    sent = []

    class Analyzer:
        def __init__(self, config):
            pass

        def analyze(self, path, name):
            return {
                'test_id': 'CZ-TEST-ONE', 'source_name': name,
                'source_path': str(path), 'source_sha256': digest,
                'result': 'POSSIBLE_ACCIDENT', 'duration_seconds': 2,
                'windows_analyzed': 1, 'evidence_paths': [],
                'decision_basis': 'mock', 'model_name': 'mock',
                'events': [{'event_id': 'CZ-TEST-ONE-001', 'timestamp': 1.0,
                            'score': .9, 'reason': 'mock', 'original_detected': True,
                            'evidence_paths': [], 'frame_timestamps': [1.0, 2.0]}],
            }

    monkeypatch.setattr(test_ui, 'TestVideoAnalyzer', Analyzer)
    monkeypatch.setattr(test_ui, '_send_verified_test_alert', sent.append)
    monkeypatch.setattr(test_ui, 'run_automatic_verification',
                        lambda *args, **kwargs: {'status': 'VERIFIED',
                                                 'classification': 'NO_ACCIDENT_EVIDENCE'})
    UploadAnalysis(config, [(Path('traffic.mp4'), 'traffic.mp4')])._run()
    assert sent == []

    # Use a fresh store for a second analysis of the same mocked footage.
    config = LabConfig.load(data_dir=tmp_path / 'second_lab')
    monkeypatch.setattr(test_ui, 'run_automatic_verification',
                        lambda *args, **kwargs: {'status': 'VERIFIED',
                                                 'classification': 'LIKELY_ACCIDENT'})
    UploadAnalysis(config, [(Path('traffic.mp4'), 'traffic.mp4')])._run()
    assert sent == [digest]
