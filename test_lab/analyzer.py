"""Full-video inference using CrashZero's existing temporal checkpoint."""
from pathlib import Path
import hashlib
import math
import os
import uuid

import cv2
import numpy as np
import torch

from module_2_accident_response.temporal import load_temporal_model
from .candidates import group_candidates, suspicion_threshold
from .config import TestLabConfig
from .evidence import capture_pair


FRAME_COUNT = 16
SAMPLE_FPS = 4
WINDOW_SECONDS = FRAME_COUNT / SAMPLE_FPS
UNCERTAIN_MARGIN = 0.15


def classify_scores(scores, threshold, duration_seconds, verification_threshold=None):
    """Return result metadata from one-second-stride temporal windows.

    A detection needs two adjacent above-threshold windows.  A lone crossing
    or a score near the validation-selected threshold remains uncertain.
    """
    if not scores:
        return {'result': 'Uncertain', 'event_timestamp': None, 'model_score': None,
                'basis': 'The video is too short for one complete four-second temporal window.'}
    ordered = sorted(scores, key=lambda item: item['timestamp'])
    uses_verifier = verification_threshold is not None
    above = [item for item in ordered if item['score'] >= threshold and
             (not uses_verifier or item.get('verification_score', 0.0) >= verification_threshold)]
    persistent_pair = None
    for first, second in zip(above, above[1:]):
        if second['timestamp'] - first['timestamp'] <= 2.01:
            persistent_pair = (first, second)
            break
    if persistent_pair:
        onset = persistent_pair[0]
        return {'result': 'Accident Detected', 'event_timestamp': onset['timestamp'],
                'model_score': onset['score'],
                'basis': (('Two independently trained temporal models agreed across at least two adjacent '
                           'four-second motion windows; the onset of the first persistent episode is reported.')
                          if uses_verifier else
                          ('At least two adjacent four-second motion windows exceeded the '
                           'checkpoint threshold; the first persistent episode is reported.'))}
    peak = max(ordered, key=lambda item: item['score'])
    boundary = max(0.0, threshold - UNCERTAIN_MARGIN)
    primary_signal = any(item['score'] >= boundary for item in ordered)
    verifier_boundary = (max(0.0, verification_threshold - UNCERTAIN_MARGIN)
                         if uses_verifier else None)
    verifier_signal = (uses_verifier and
                       any(item.get('verification_score', 0.0) >= verifier_boundary for item in ordered))
    if primary_signal or verifier_signal:
        return {'result': 'Uncertain', 'event_timestamp': peak['timestamp'],
                'model_score': peak['score'],
                'basis': (('The baseline and hard-negative verifier did not agree with persistent evidence, '
                           'so no accident or safe outcome is asserted.') if uses_verifier else
                          ('Evidence was borderline or did not persist across adjacent '
                           'multi-frame windows, so no accident is asserted.'))}
    return {'result': 'No Accident Detected', 'event_timestamp': None,
            'model_score': peak['score'],
            'basis': ('Every analyzed four-second motion window stayed below the '
                      'predefined uncertain band.')}


class TestVideoAnalyzer:
    def __init__(self, config=None, device='auto'):
        self.config = config or TestLabConfig.load()
        if device == 'auto':
            device = 'mps' if torch.backends.mps.is_available() else 'cpu'
        if device == 'mps' and not torch.backends.mps.is_available():
            raise RuntimeError('MPS was requested but is unavailable.')
        self.device = device

    def analyze(self, path, source_name=None, progress=None, candidate_threshold=None, cooldown=None):
        path = Path(path)
        model, threshold = load_temporal_model(self.config.model_path, self.device)
        if model is None:
            raise RuntimeError('The existing temporal accident checkpoint is unavailable.')
        verifier, verification_threshold = load_temporal_model(
            self.config.verification_model_path, self.device)
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError('Unable to decode this video.')
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        frame_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not math.isfinite(fps) or fps < SAMPLE_FPS:
            cap.release()
            raise ValueError('Video must have a valid frame rate of at least 4 FPS.')

        frames = []
        next_sample = 0.0
        index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            timestamp = index / fps
            index += 1
            if timestamp + 1e-6 >= next_sample:
                frames.append(cv2.cvtColor(cv2.resize(frame, (160, 96)), cv2.COLOR_BGR2RGB))
                next_sample += 1.0 / SAMPLE_FPS
            if progress and index % 30 == 0:
                progress(min(0.45, 0.45 * index / max(1, frame_total)))
        cap.release()
        duration = index / fps

        starts = list(range(0, max(0, len(frames) - FRAME_COUNT + 1), SAMPLE_FPS))
        last_start = len(frames) - FRAME_COUNT
        if last_start >= 0 and (not starts or starts[-1] != last_start):
            starts.append(last_start)
        scores = []
        model.eval()
        with torch.inference_mode():
            for batch_start in range(0, len(starts), 16):
                batch_starts = starts[batch_start:batch_start + 16]
                clips = np.asarray([frames[start:start + FRAME_COUNT] for start in batch_starts])
                tensor = torch.from_numpy(clips).permute(0, 1, 4, 2, 3).float().div_(255.0)
                values = torch.sigmoid(model(tensor.to(self.device))).cpu().numpy().tolist()
                verification_values = (torch.sigmoid(verifier(tensor.to(self.device))).cpu().numpy().tolist()
                                       if verifier is not None else [None] * len(values))
                for start, value, verification_value in zip(batch_starts, values, verification_values):
                    scores.append({'timestamp': start / SAMPLE_FPS + WINDOW_SECONDS / 2,
                                   'score': float(value),
                                   **({'verification_score': float(verification_value)}
                                      if verification_value is not None else {})})
                if progress:
                    progress(0.45 + 0.45 * min(len(starts), batch_start + 16) / max(1, len(starts)))

        decision = classify_scores(scores, threshold, duration, verification_threshold)
        test_id = 'CZ-TEST-' + uuid.uuid4().hex[:10].upper()
        lower = (suspicion_threshold(threshold) if candidate_threshold is None
                 else max(0., min(threshold, float(candidate_threshold))))
        if cooldown is None:
            cooldown = max(0.0, float(os.getenv('SUSPICION_COOLDOWN_SECONDS', '3.0')))
        candidates = group_candidates(scores, threshold, lower, cooldown,
                                      verification_threshold)
        events = []
        for number, candidate in enumerate(candidates, 1):
            event_id = f'{test_id}-{number:03d}'
            paths, actual_times, limitation = capture_pair(
                path, self.config.evidence_dir / event_id, candidate['timestamp'])
            events.append({'event_id': event_id, 'timestamp': candidate['timestamp'],
                           'score': candidate['score'], 'reason': candidate['reason'],
                           'original_detected': candidate['original_detected'],
                           'evidence_paths': paths, 'frame_timestamps': actual_times,
                           'evidence_limitation': limitation, 'status': 'PENDING'})
        evidence_paths = [path for event in events for path in event['evidence_paths']]
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(block)
        if progress:
            progress(1.0)
        return {
            'test_id': test_id, 'source_name': source_name or path.name,
            'source_path': str(path), 'source_sha256': digest.hexdigest(),
            'result': decision['result'], 'event_timestamp': decision['event_timestamp'],
            'model_score': decision['model_score'], 'threshold': threshold,
            'suspicion_threshold': lower, 'events': events,
            'duration_seconds': duration, 'windows_analyzed': len(scores),
            'evidence_paths': [str(item) for item in evidence_paths],
            'decision_basis': decision['basis'],
            'model_name': ('two-model temporal consensus · 16 frames at 4 FPS'
                           if verifier is not None else 'crash_temporal.pt · 16 frames at 4 FPS'),
        }
