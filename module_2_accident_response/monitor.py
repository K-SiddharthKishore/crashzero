"""Continuous Module 2 monitoring. No emergency call is made by this worker."""
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import threading
import uuid

import cv2
import torch

from src.video.source import VideoFileSource, WebcamSource, StreamSource
from test_lab.automatic import run_automatic_verification, alert_state
from test_lab.evidence import save_frame_pair
from .pipeline import Module2Analyzer, ROAD, evidence_timestamp
from .storage import AccidentRepository
from .temporal import load_temporal_model, score_rgb_frames


class AutomaticMonitor:
    def __init__(self, config, source, *, camera_id='M2', location='Location not configured',
                 source_key=None, verifier=run_automatic_verification, model=None,
                 temporal=None):
        self.config, self.source = config, source
        self.camera_id, self.location = camera_id, location
        self.source_key = source_key or hashlib.sha256(str(source.source).encode()).hexdigest()[:20]
        self.verifier, self.model, self.temporal = verifier, model, temporal
        self.repo = AccidentRepository(config.db_path)
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.thread = None
        self.status = 'READY'
        self.error = None
        self.incident_ids = []
        self.frames_processed = 0
        self.preview = None
        self.executor = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.run, daemon=True, name='CrashZero-M2-monitor')
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def snapshot(self):
        with self.lock:
            records = [self.repo.verification(identity) for identity in self.incident_ids]
            analyzing = self.status in ('READY', 'MONITORING') and (
                not self.source.live or self.frames_processed == 0)
            state, note = alert_state(records, analyzing=analyzing)
            if self.error and state != 'ALERT':
                state = 'VERIFICATION UNAVAILABLE'
                note = 'Monitoring unavailable.'
            return {'status': self.status, 'state': state, 'note': note,
                    'error': self.error, 'frames': self.frames_processed,
                    'incidents': len(self.incident_ids), 'preview': self.preview}

    def _record(self, candidate, first, second):
        identity = 'CZ-AR-' + datetime.now(timezone.utc).strftime('%Y%m%d') + '-' + uuid.uuid4().hex[:8].upper()
        folder = self.config.evidence_dir / identity
        paths, times = save_frame_pair([first, second], folder)
        screenshot = folder / 'screenshot.jpg'
        cv2.imwrite(str(screenshot), first[1])
        clip_path = None
        if not self.source.live:
            clip, _ = Module2Analyzer(self.config)._extract(
                self.source.source, candidate['timestamp'], identity, self.source.fps)
            clip_path = str(clip)
        incident = {
            'incident_id': identity, 'source_kind': 'live camera' if self.source.live else 'uploaded video',
            'event_offset': candidate['timestamp'], 'camera_id': self.camera_id,
            'location': self.location, 'state': 'POSSIBLE_ACCIDENT',
            'score': candidate['score'], 'track_ids': candidate.get('track_ids', []),
            'clip_path': clip_path, 'screenshot_path': str(screenshot),
            'original_recording_time': None,
            'reliability': {'tracking': 'supporting only', 'temporal_classifier':
                            'research benchmark' if candidate.get('temporal') else 'unavailable'},
            'explanation': candidate.get('trigger_reason', 'Grouped suspicious event'),
            'source_key': self.source_key, 'evidence_paths': paths,
            'frame_timestamps': times,
            'evidence_limitation': ('The second frame was captured before one second elapsed.'
                                    if times[1]-times[0] < .8 else None),
        }
        self.repo.save_incident(incident)
        with self.lock:
            self.incident_ids.append(identity)
        self.executor.submit(self._verify, identity)

    def _verify(self, identity):
        try:
            if not self.source.live:
                with self.lock:
                    prior = [item for item in self.incident_ids if item != identity]
                if any((row := self.repo.verification(item)) and
                       row.get('status') == 'VERIFIED' and
                       row.get('classification') == 'LIKELY_ACCIDENT'
                       for item in prior):
                    return  # A confirmed upload already has its final alert.
            self.verifier(self.repo, identity, kind='m2',
                          budget_root=self.config.db_path.parent.parent)
        except Exception:
            self.repo.fail_verification(identity, 'Verification unavailable.')

    def run(self):
        analyzer = Module2Analyzer(self.config)
        histories = defaultdict(lambda: deque(maxlen=18))
        sampled = deque(maxlen=16)
        recent_scores = deque(maxlen=3)
        next_sample = 0.0
        last_score_time = -1.0
        pending = None
        last_event_time = -1e9
        # A long global cooldown hides a second, unrelated road-user collision
        # shortly after an early false candidate in a short CCTV recording.
        cooldown = 3.0
        ring = deque(maxlen=240)
        try:
            model = self.model or analyzer._model()
            temporal_model, temporal_threshold = (self.temporal if self.temporal is not None else
                                                    load_temporal_model(self.config.temporal_model_path,
                                                                        'mps' if torch.backends.mps.is_available() else 'cpu'))
            device = 'mps' if torch.backends.mps.is_available() else 'cpu'
            self.source.open()
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='CrashZero-verify')
            with self.lock:
                self.status = 'MONITORING'
            while not self.stop_event.is_set():
                item = self.source.read()
                if item is None:
                    break
                now, frame = item
                ring.append((now, frame.copy()))
                with self.lock:
                    self.frames_processed += 1
                    if self.frames_processed % 15 == 0:
                        self.preview = cv2.cvtColor(cv2.resize(frame, (640, 360)), cv2.COLOR_BGR2RGB)
                if pending:
                    if pending['first'] is None and now >= pending['candidate']['timestamp']:
                        pending['first'] = (now, frame.copy())
                    elif pending['first'] is not None and now >= pending['first'][0] + 0.95:
                        try:
                            self._record(pending['candidate'], pending['first'], (now, frame.copy()))
                        except Exception as exc:
                            with self.lock:
                                self.error = f'Evidence or verification unavailable: {type(exc).__name__}.'
                        last_event_time = now
                        pending = None
                results = model.track(frame, persist=True, tracker='bytetrack.yaml',
                                      classes=list(ROAD), verbose=False)
                result = results[0] if isinstance(results, (list, tuple)) else results
                boxes = result.boxes
                active_ids = []
                if boxes is not None and boxes.id is not None:
                    ids = boxes.id.int().cpu().tolist()
                    xyxy = boxes.xyxy.cpu().tolist()
                    conf = boxes.conf.cpu().tolist()
                    classes = boxes.cls.int().cpu().tolist()
                    active_ids = ids
                    for tid, box, score, klass in zip(ids, xyxy, conf, classes):
                        histories[tid].append((now, analyzer._center(box), float(score),
                                               ROAD.get(klass, 'unknown'), box))
                candidate = None
                if temporal_model is not None:
                    if now + 1e-6 >= next_sample:
                        rgb = cv2.cvtColor(cv2.resize(frame, (160, 96)), cv2.COLOR_BGR2RGB)
                        sampled.append(rgb)
                        next_sample = now + .25
                    if len(sampled) == 16 and now-last_score_time >= 1.0:
                        score = score_rgb_frames(temporal_model, list(sampled), device)
                        last_score_time = now
                        recent_scores.append({'score': score, 'timestamp': max(0., now-1.875),
                                              'track_ids': active_ids})
                        lower = min(temporal_threshold, self.config.suspicion_threshold)
                        if sum(x['score'] >= lower for x in recent_scores) >= 2:
                            crossings = [x for x in recent_scores if x['score'] >= lower]
                            onset = crossings[0]
                            candidate = dict(onset, score=max(x['score'] for x in crossings), temporal=True,
                                             trigger_reason='Persistent temporal accident prediction')
                if candidate is None:
                    candidate = analyzer._candidate(histories, now)
                if candidate and pending is None and now-last_event_time >= cooldown:
                    candidate = candidate | {'timestamp': evidence_timestamp(candidate)}
                    last_event_time = now
                    if candidate['timestamp'] <= now:
                        first = min(ring, key=lambda pair: abs(pair[0]-candidate['timestamp']))
                        later = [pair for pair in ring if pair[0] >= first[0] + .95]
                        if later:
                            second = min(later, key=lambda pair: abs(pair[0]-(first[0]+1.0)))
                            self._record(candidate, first, second)
                        else:
                            pending = {'candidate': candidate, 'first': first}
                    else:
                        pending = {'candidate': candidate, 'first': None}
            if pending and not self.stop_event.is_set() and ring:
                # A short recording cannot provide a full one-second gap. Record the
                # limitation rather than losing a real candidate at end of file.
                first = pending['first'] or ring[-1]
                self._record(pending['candidate'], first, ring[-1])
            self.executor.shutdown(wait=True)
            with self.lock:
                self.status = 'STOPPED' if self.stop_event.is_set() else 'COMPLETED'
        except Exception as exc:
            with self.lock:
                self.error = f'Monitoring unavailable: {type(exc).__name__}.'
                self.status = 'ERROR'
        finally:
            if self.executor is not None:
                self.executor.shutdown(wait=True)
            self.source.close()


def source_for(mode, value=None, *, hosted=False):
    if mode == 'Upload':
        return VideoFileSource(value)
    if mode == 'Camera':
        return WebcamSource(0)
    if mode == 'Network camera':
        return StreamSource(value, hosted=hosted)
    raise ValueError('Unsupported video source.')
