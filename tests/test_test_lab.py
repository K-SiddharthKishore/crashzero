import json

from streamlit.testing.v1 import AppTest
from config.settings import ROOT
from test_lab.analyzer import classify_scores
from test_lab.storage import TestHistory
from scripts.finetune_test_reviews import load_manifest


def test_temporal_persistence_not_single_window_or_overlap_proxy():
    threshold = .72
    single = classify_scores([{'timestamp': 2., 'score': .8},
                              {'timestamp': 5., 'score': .1}], threshold, 7.)
    assert single['result'] == 'Uncertain'
    persistent = classify_scores([{'timestamp': 2., 'score': .8},
                                  {'timestamp': 3., 'score': .75}], threshold, 7.)
    assert persistent['result'] == 'Accident Detected'
    normal = classify_scores([{'timestamp': 2., 'score': .2},
                              {'timestamp': 3., 'score': .3}], threshold, 7.)
    assert normal['result'] == 'No Accident Detected'


def test_two_model_consensus_withholds_disagreement():
    scores = [
        {'timestamp': 2., 'score': .90, 'verification_score': .20},
        {'timestamp': 3., 'score': .88, 'verification_score': .25},
    ]
    assert classify_scores(scores, .72, 6., .66)['result'] == 'Uncertain'
    for item in scores:
        item['verification_score'] = .80
    assert classify_scores(scores, .72, 6., .66)['result'] == 'Accident Detected'


def test_history_accuracy_only_uses_verified_predictions(tmp_path):
    history = TestHistory(tmp_path / 'history.sqlite3')
    base = {'source_name': 'video.mp4', 'source_path': str(tmp_path / 'video.mp4'),
            'source_sha256': 'a' * 64, 'result': 'No Accident Detected',
            'event_timestamp': None, 'model_score': .2, 'threshold': .72,
            'duration_seconds': 10., 'windows_analyzed': 7, 'evidence_paths': [],
            'decision_basis': 'low', 'model_name': 'test'}
    for index in range(3):
        history.save(base | {'test_id': f'TEST-{index}'})
    history.review('TEST-0', 'CORRECT')
    history.review('TEST-1', 'WRONG', 'ACCIDENT', 4.2, 'missed', True)
    history.review('TEST-2', 'NOT_SURE')
    metrics = history.metrics()
    assert metrics['total'] == 3 and metrics['verified'] == 2
    assert metrics['accuracy'] == .5
    assert history.training_manifest()[0]['ground_truth'] == 'ACCIDENT'


def test_finetuning_manifest_requires_explicit_approval_and_hash(tmp_path):
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'video')
    import hashlib
    digest = hashlib.sha256(b'video').hexdigest()
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps([
        {'video': str(video), 'sha256': digest, 'ground_truth': 'NO_ACCIDENT',
         'approved_for_training': False},
        {'video': str(video), 'sha256': digest, 'ground_truth': 'NO_ACCIDENT',
         'approved_for_training': True},
    ]))
    rows = load_manifest(manifest)
    assert len(rows) == 1 and rows[0]['approved_for_training'] is True


def test_test_section_opens_without_touching_response_module(tmp_path, monkeypatch):
    monkeypatch.setenv('CRASHZERO_V2_HOSTED', '1')
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    next(button for button in app.button if button.label == 'Open Accident Detector').click().run()
    assert not app.exception
    assert [title.value for title in app.title] == ['Accident Detection']
    assert len(app.get('file_uploader')) == 1
    assert not any('TEST evaluation' in exp.label for exp in app.expander)
    assert not any(button.label == 'Test Call' for button in app.button)
