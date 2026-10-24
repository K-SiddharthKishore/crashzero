"""The debug preview must show request JPEGs, especially for cache hits."""
import base64
import json
from contextlib import nullcontext
from types import SimpleNamespace

import cv2
import numpy as np

from module_2_accident_response.storage import AccidentRepository
from test_lab.automatic import run_automatic_verification
from test_lab import evidence_preview
from test_lab.evidence_preview import SHOW_DEBUG_EVIDENCE, preview_items
from test_lab.storage import TestHistory
from test_lab.verification import settings


def _jpeg(path, shade):
    assert cv2.imwrite(str(path), np.full((24, 32, 3), shade, np.uint8))
    return str(path)


def _result(label='LIKELY_ACCIDENT'):
    return {'classification': label, 'explanation': 'Mocked visible evidence.',
            'visible_evidence': [], 'limitations': [],
            'input_tokens': 100, 'output_tokens': 20}


def _test_run(identity, paths):
    return {'test_id': identity, 'source_name': 'same.mp4', 'source_path': 'same.mp4',
            'source_sha256': 'a' * 64, 'result': 'Uncertain', 'event_timestamp': 6.,
            'model_score': .8, 'threshold': .7, 'duration_seconds': 10.,
            'windows_analyzed': 5, 'evidence_paths': [], 'decision_basis': 'mock',
            'model_name': 'mock', 'events': [{'event_id': identity + '-event',
            'timestamp': 6., 'score': .8, 'reason': 'Grouped event',
            'original_detected': False, 'evidence_paths': paths,
            'frame_timestamps': [6., 7.]}]}


def test_test_preview_reads_original_request_bytes_for_cache_hit(tmp_path):
    assert SHOW_DEBUG_EVIDENCE is True
    original = [_jpeg(tmp_path / f'original-{i}.jpg', i * 90) for i in (1, 2)]
    reconstructed = [_jpeg(tmp_path / f'new-{i}.jpg', i * 30) for i in (1, 2)]
    history = TestHistory(tmp_path / 'test.sqlite3')
    config = settings() | {'model': 'mock', 'budget_usd': .1}
    history.save(_test_run('first', original))
    assert history.claim_verification('first-event', config) == 'claimed'
    history.finish_verification('first-event', _result(), config)
    history.save(_test_run('second', reconstructed))
    assert history.reuse_cached('second-event', 'mock')
    item = preview_items([history.event('second-event')], history.submitted_evidence)[0]
    assert item['classification'] == 'LIKELY_ACCIDENT' and item['cached']
    assert item['pair'] == [(open(path, 'rb').read(), timestamp)
                            for path, timestamp in zip(original, [6., 7.])]
    assert item['pair'][0][0] != open(reconstructed[0], 'rb').read()
    (tmp_path / 'original-1.jpg').unlink()
    assert preview_items([history.event('second-event')],
                         history.submitted_evidence)[0]['pair'] is None
    assert preview_items([{'event_id': 'not-sent', 'status': 'PENDING'}],
                         history.submitted_evidence) == []


def test_module2_preview_reads_original_request_bytes_for_cache_hit(tmp_path):
    original = [_jpeg(tmp_path / f'm2-original-{i}.jpg', i * 80) for i in (1, 2)]
    reconstructed = [_jpeg(tmp_path / f'm2-new-{i}.jpg', i * 20) for i in (1, 2)]
    repo = AccidentRepository(tmp_path / 'module2.sqlite3')
    base = {'source_kind': 'uploaded video', 'state': 'POSSIBLE_ACCIDENT',
            'score': .8, 'explanation': 'Grouped event', 'reliability': {},
            'track_ids': [1, 2], 'source_key': 'same-video',
            'frame_timestamps': [6., 7.]}
    repo.save_incident(base | {'incident_id': 'first', 'evidence_paths': original})
    config = settings() | {'model': 'mock', 'budget_usd': .1}
    assert repo.claim_verification('first', config) == 'claimed'
    repo.finish_verification('first', _result('UNCERTAIN'), config)
    repo.save_incident(base | {'incident_id': 'second', 'evidence_paths': reconstructed})
    assert repo.reuse_cached('second', 'mock')
    item = preview_items([repo.verification('second')], repo.submitted_evidence)[0]
    assert item['classification'] == 'UNCERTAIN' and item['cached']
    assert item['pair'] == [(open(path, 'rb').read(), timestamp)
                            for path, timestamp in zip(original, [6., 7.])]


def test_preview_bytes_match_mock_openai_request(tmp_path):
    paths = [_jpeg(tmp_path / f'frame-{i}.jpg', i * 60) for i in (1, 2)]
    history = TestHistory(tmp_path / 'test.sqlite3')
    history.save(_test_run('sent', paths))
    payloads = []

    class Responses:
        def create(self, **kwargs):
            payloads.extend(base64.b64decode(part['image_url'].split(',', 1)[1])
                            for part in kwargs['input'][0]['content']
                            if part['type'] == 'input_image')
            return SimpleNamespace(status='completed', output_text=json.dumps(_result()),
                                   usage=SimpleNamespace(input_tokens=100, output_tokens=20))

    result = run_automatic_verification(
        history, 'sent-event', kind='test', budget_root=tmp_path,
        client=SimpleNamespace(responses=Responses()))
    assert result['status'] == 'VERIFIED'
    item = preview_items([result], history.submitted_evidence)[0]
    assert len(payloads) == 2
    assert [data for data, _ in item['pair']] == payloads


def test_public_preview_labels_use_stage_2_terminology(monkeypatch):
    shown = []
    class FakeStreamlit:
        def subheader(self, value): shown.append(value)
        def expander(self, value, **_kwargs):
            shown.append(value)
            return nullcontext()
        def columns(self, _count): return (nullcontext(), nullcontext())
        def caption(self, value): shown.append(value)
        def markdown(self, value): shown.append(value)
        def image(self, _bytes, **_kwargs): pass
        def write(self, value): shown.append(value)

    monkeypatch.setattr(evidence_preview, 'st', FakeStreamlit())
    record = {'event_id': 'event-1', 'status': 'VERIFIED',
              'classification': 'LIKELY_ACCIDENT', 'attempt_count': 1}
    original = {'evidence_paths': [], 'frame_timestamps': []}
    evidence_preview.render_evidence_preview([record], lambda _identity: original)
    assert 'Evidence Frames Analysed' in shown
    assert 'Event 1 — Stage 2 Result: LIKELY_ACCIDENT' in shown
    assert all('OpenAI' not in value for value in shown)
