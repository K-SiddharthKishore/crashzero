"""Persistence for offline TEST runs; no Module 1/2 tables are touched."""
import json
import hashlib
import sqlite3
import threading
import time
from pathlib import Path


REVIEWS = {'CORRECT', 'WRONG', 'NOT_SURE'}
OUTCOMES = {'ACCIDENT', 'NO_ACCIDENT', 'NOT_SURE'}


class TestHistory:
    __test__ = False

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        with self._connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS test_runs (
              test_id TEXT PRIMARY KEY, created_at REAL NOT NULL,
              source_name TEXT NOT NULL, source_path TEXT NOT NULL,
              source_sha256 TEXT NOT NULL, result TEXT NOT NULL,
              event_timestamp REAL, model_score REAL, threshold REAL,
              duration_seconds REAL NOT NULL, windows_analyzed INTEGER NOT NULL,
              evidence_json TEXT NOT NULL, decision_basis TEXT NOT NULL,
              model_name TEXT NOT NULL, review TEXT, actual_outcome TEXT,
              actual_timestamp REAL, reviewer_note TEXT,
              approved_for_training INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS test_runs_created_idx ON test_runs(created_at DESC);
            CREATE INDEX IF NOT EXISTS test_runs_review_idx ON test_runs(review, actual_outcome);
            CREATE TABLE IF NOT EXISTS test_events (
              event_id TEXT PRIMARY KEY, test_id TEXT NOT NULL,
              timestamp REAL NOT NULL, score REAL NOT NULL, reason TEXT NOT NULL,
              original_detected INTEGER NOT NULL, evidence_json TEXT NOT NULL,
              frame_timestamps_json TEXT NOT NULL, evidence_limitation TEXT,
              status TEXT NOT NULL DEFAULT 'PENDING', classification TEXT,
              explanation TEXT, visible_evidence_json TEXT, limitations_json TEXT,
              model TEXT, input_tokens INTEGER, output_tokens INTEGER,
              estimated_usd REAL NOT NULL DEFAULT 0, error TEXT,
              cache_key TEXT, attempt_count INTEGER NOT NULL DEFAULT 0,
              review TEXT, actual_outcome TEXT, updated_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS test_events_run_idx ON test_events(test_id);
            CREATE INDEX IF NOT EXISTS test_events_cache_idx ON test_events(cache_key,status);
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(test_runs)')}
            if 'suspicion_threshold' not in columns:
                db.execute('ALTER TABLE test_runs ADD COLUMN suspicion_threshold REAL')

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        return db

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        result = dict(row)
        result['evidence_paths'] = json.loads(result.pop('evidence_json'))
        result['approved_for_training'] = bool(result['approved_for_training'])
        return result

    @staticmethod
    def _event(row):
        event = dict(row)
        event['original_detected'] = bool(event['original_detected'])
        event['evidence_paths'] = json.loads(event.pop('evidence_json'))
        event['frame_timestamps'] = json.loads(event.pop('frame_timestamps_json'))
        event['visible_evidence'] = json.loads(event.pop('visible_evidence_json') or '[]')
        event['limitations'] = json.loads(event.pop('limitations_json') or '[]')
        return event

    def save(self, row):
        with self.lock, self._connect() as db:
            db.execute('''INSERT INTO test_runs (
              test_id,created_at,source_name,source_path,source_sha256,result,
              event_timestamp,model_score,threshold,duration_seconds,
              windows_analyzed,evidence_json,decision_basis,model_name)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                row['test_id'], row.get('created_at', time.time()), row['source_name'],
                row['source_path'], row['source_sha256'], row['result'],
                row.get('event_timestamp'), row.get('model_score'), row.get('threshold'),
                row['duration_seconds'], row['windows_analyzed'],
                json.dumps(row.get('evidence_paths', [])), row['decision_basis'],
                row['model_name']))
            db.execute('UPDATE test_runs SET suspicion_threshold=? WHERE test_id=?',
                       (row.get('suspicion_threshold'), row['test_id']))
            for event in row.get('events', []):
                db.execute('''INSERT INTO test_events (event_id,test_id,timestamp,score,reason,
                    original_detected,evidence_json,frame_timestamps_json,evidence_limitation,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (event['event_id'], row['test_id'], event['timestamp'], event['score'],
                     event['reason'], int(event['original_detected']),
                     json.dumps(event['evidence_paths']), json.dumps(event['frame_timestamps']),
                     event.get('evidence_limitation'), time.time()))

    def all(self):
        with self._connect() as db:
            rows = [self._decode(row) for row in db.execute(
                'SELECT * FROM test_runs ORDER BY created_at DESC')]
            for row in rows:
                row['events'] = self.events(row['test_id'])
            return rows

    def get(self, test_id):
        with self._connect() as db:
            row = self._decode(db.execute(
                'SELECT * FROM test_runs WHERE test_id=?', (test_id,)).fetchone())
            if row:
                row['events'] = self.events(test_id)
            return row

    def events(self, test_id):
        with self._connect() as db:
            return [self._event(row) for row in db.execute(
                'SELECT * FROM test_events WHERE test_id=? ORDER BY timestamp', (test_id,))]

    def event(self, event_id):
        with self._connect() as db:
            return self._event(db.execute(
                'SELECT * FROM test_events WHERE event_id=?', (event_id,)).fetchone())

    def submitted_evidence(self, event_id):
        """Return the original verified request row, including for a cache hit."""
        with self._connect() as db:
            row = db.execute('SELECT * FROM test_events WHERE event_id=?', (event_id,)).fetchone()
            if row is None or row['status'] != 'VERIFIED':
                return None
            if row['attempt_count'] == 0:
                row = db.execute('''SELECT * FROM test_events WHERE cache_key=?
                    AND status='VERIFIED' AND attempt_count>0
                    ORDER BY updated_at ASC LIMIT 1''', (row['cache_key'],)).fetchone()
            return self._event(row) if row is not None else None

    def spending(self):
        with self._connect() as db:
            return float(db.execute('SELECT COALESCE(SUM(estimated_usd),0) FROM test_events').fetchone()[0])

    def reuse_cached(self, event_id, model):
        """Reuse an identical verified event without reserving paid budget."""
        from .verification import VERIFICATION_POLICY
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            event = db.execute('''SELECT e.*,r.source_sha256 FROM test_events e JOIN test_runs r
                ON e.test_id=r.test_id WHERE e.event_id=?''', (event_id,)).fetchone()
            if event is None or event['status'] != 'PENDING':
                return False
            cache_key = hashlib.sha256(
                f"{event['source_sha256']}:{event['timestamp']:.3f}:{model}:{VERIFICATION_POLICY}".encode()).hexdigest()
            cached = db.execute("SELECT * FROM test_events WHERE cache_key=? AND status='VERIFIED' LIMIT 1",
                                (cache_key,)).fetchone()
            if cached is None:
                return False
            db.execute('''UPDATE test_events SET status='VERIFIED',classification=?,explanation=?,
                visible_evidence_json=?,limitations_json=?,model=?,input_tokens=?,output_tokens=?,
                cache_key=?,error=NULL,updated_at=? WHERE event_id=?''',
                (cached['classification'],cached['explanation'],cached['visible_evidence_json'],
                 cached['limitations_json'],cached['model'],cached['input_tokens'],
                 cached['output_tokens'],cache_key,time.time(),event_id))
            return True

    def claim_verification(self, event_id, config):
        """Atomically reserve budget and one request slot, or reuse a prior result."""
        from .verification import VERIFICATION_POLICY, estimated_request_cost
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            event = db.execute('''SELECT e.*,r.source_sha256 FROM test_events e JOIN test_runs r
                ON e.test_id=r.test_id WHERE e.event_id=?''', (event_id,)).fetchone()
            if event is None:
                raise KeyError(event_id)
            if event['status'] == 'VERIFIED' or (event['status'] == 'PROCESSING'
                    and time.time() - event['updated_at'] < 120):
                return 'already_done'
            cache_key = hashlib.sha256(
                f"{event['source_sha256']}:{event['timestamp']:.3f}:{config['model']}:{VERIFICATION_POLICY}".encode()).hexdigest()
            cached = db.execute('''SELECT * FROM test_events WHERE cache_key=? AND status='VERIFIED'
                LIMIT 1''', (cache_key,)).fetchone()
            if cached:
                db.execute('''UPDATE test_events SET status='VERIFIED',classification=?,explanation=?,
                    visible_evidence_json=?,limitations_json=?,model=?,input_tokens=?,output_tokens=?,
                    cache_key=?,error=NULL,updated_at=? WHERE event_id=?''',
                    (cached['classification'],cached['explanation'],cached['visible_evidence_json'],
                     cached['limitations_json'],cached['model'],cached['input_tokens'],
                     cached['output_tokens'],cache_key,time.time(),event_id))
                return 'cached'
            count = db.execute('''SELECT COALESCE(SUM(attempt_count),0) FROM test_events
                WHERE test_id=?''', (event['test_id'],)).fetchone()[0]
            if count >= config['max_requests_per_video']:
                db.execute('''UPDATE test_events SET status='VERIFICATION_FAILED',error=?,updated_at=?
                    WHERE event_id=?''', ('Per-video request limit reached.',time.time(),event_id))
                return 'request_limit'
            estimate = estimated_request_cost(config)
            spent = db.execute('SELECT COALESCE(SUM(estimated_usd),0) FROM test_events').fetchone()[0]
            if spent + estimate > config['budget_usd']:
                db.execute('''UPDATE test_events SET status='VERIFICATION_FAILED',error=?,updated_at=?
                    WHERE event_id=?''', ('Session budget exhausted.',time.time(),event_id))
                return 'budget_exhausted'
            db.execute('''UPDATE test_events SET status='PROCESSING',cache_key=?,model=?,
                estimated_usd=estimated_usd+?,attempt_count=attempt_count+1,error=NULL,updated_at=?
                WHERE event_id=?''', (cache_key,config['model'],estimate,time.time(),event_id))
            return 'claimed'

    def finish_verification(self, event_id, result, config):
        from .verification import cost_usd, estimated_request_cost
        input_tokens, output_tokens = result.get('input_tokens'), result.get('output_tokens')
        actual = (cost_usd(input_tokens, output_tokens, config)
                  if input_tokens is not None and output_tokens is not None
                  else estimated_request_cost(config))
        with self.lock, self._connect() as db:
            db.execute('''UPDATE test_events SET status='VERIFIED',classification=?,explanation=?,
                visible_evidence_json=?,limitations_json=?,input_tokens=?,output_tokens=?,
                estimated_usd=estimated_usd-?+?,error=NULL,updated_at=? WHERE event_id=?''',
                (result['classification'],result['explanation'],
                 json.dumps(result['visible_evidence']),json.dumps(result['limitations']),
                 input_tokens,output_tokens,estimated_request_cost(config),actual,time.time(),event_id))

    def fail_verification(self, event_id, message='Verification request failed or returned invalid data.'):
        with self.lock, self._connect() as db:
            db.execute('''UPDATE test_events SET status='VERIFICATION_FAILED',error=?,updated_at=?
                WHERE event_id=?''', (message,time.time(),event_id))

    def review_event(self, event_id, review, actual_outcome=None):
        if review not in REVIEWS or (actual_outcome is not None and actual_outcome not in OUTCOMES):
            raise ValueError('Invalid review or outcome.')
        with self.lock, self._connect() as db:
            if not db.execute('''UPDATE test_events SET review=?,actual_outcome=?,updated_at=?
                WHERE event_id=?''', (review,actual_outcome,time.time(),event_id)).rowcount:
                raise KeyError(event_id)

    def review(self, test_id, review, actual_outcome=None, actual_timestamp=None,
               note='', approved_for_training=False):
        if review not in REVIEWS:
            raise ValueError('Invalid review value.')
        if actual_outcome is not None and actual_outcome not in OUTCOMES:
            raise ValueError('Invalid actual outcome.')
        # A correctness click is verification for evaluation metrics.  Promotion
        # into a future training manifest additionally requires an explicit,
        # usable ground-truth outcome.
        approved = bool(approved_for_training and actual_outcome in {'ACCIDENT', 'NO_ACCIDENT'})
        with self.lock, self._connect() as db:
            changed = db.execute('''UPDATE test_runs SET review=?,actual_outcome=?,
                actual_timestamp=?,reviewer_note=?,approved_for_training=?
                WHERE test_id=?''', (review, actual_outcome, actual_timestamp,
                                    note.strip(), int(approved), test_id)).rowcount
        if not changed:
            raise KeyError(test_id)

    def metrics(self):
        rows = self.all()
        verified = [row for row in rows if row['review'] in {'CORRECT', 'WRONG'}]
        events = [event for row in rows for event in row['events']]
        manual_labeled = [e for e in events if e['actual_outcome'] in ('ACCIDENT','NO_ACCIDENT')]
        labeled = [e for e in manual_labeled
                   if e['classification'] in ('LIKELY_ACCIDENT','NO_ACCIDENT_EVIDENCE','UNCERTAIN')]
        tp = sum(e['classification'] == 'LIKELY_ACCIDENT' and e['actual_outcome'] == 'ACCIDENT' for e in labeled)
        fp = sum(e['classification'] == 'LIKELY_ACCIDENT' and e['actual_outcome'] == 'NO_ACCIDENT' for e in labeled)
        fn = sum(e['classification'] != 'LIKELY_ACCIDENT' and e['actual_outcome'] == 'ACCIDENT' for e in labeled)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        videos_with_truth = [row for row in rows if row['actual_outcome'] in ('ACCIDENT','NO_ACCIDENT')]
        positive_videos = [row for row in videos_with_truth
                           if row['actual_outcome'] == 'ACCIDENT' and row['actual_timestamp'] is not None]
        def matches(row, event):
            return abs(event['timestamp'] - row['actual_timestamp']) <= 3.0
        stage1_found = sum(any(matches(row,e) for e in row['events']) for row in positive_videos)
        final_found = sum(any(matches(row,e) and e['classification'] == 'LIKELY_ACCIDENT'
                              for e in row['events']) for row in positive_videos)
        return {
            'total': len(rows),
            'accidents': sum(row['result'] == 'Accident Detected' for row in rows),
            'uncertain': sum(row['result'] == 'Uncertain' for row in rows),
            'verified': len(verified),
            'correct': sum(row['review'] == 'CORRECT' for row in verified),
            'accuracy': (sum(row['review'] == 'CORRECT' for row in verified) / len(verified)
                         if verified else None),
            'suspected_events': len(events),
            'original_events': sum(e['original_detected'] for e in events),
            'verification_results': {label: sum(e['classification'] == label for e in events)
                                     for label in ('LIKELY_ACCIDENT','NO_ACCIDENT_EVIDENCE','UNCERTAIN')},
            'manually_confirmed_accidents': sum(e['actual_outcome'] == 'ACCIDENT' for e in manual_labeled),
            'false_positives': fp, 'precision': precision, 'recall': recall,
            'f1': (2 * precision * recall / (precision + recall)
                   if precision is not None and recall is not None and precision + recall else None),
            'event_labels': len(labeled),
            'ground_truth_videos': len(videos_with_truth),
            'timed_accident_videos': len(positive_videos),
            'stage1_recall': stage1_found / len(positive_videos) if positive_videos else None,
            'final_recall': final_found / len(positive_videos) if positive_videos else None,
            'missed_accident_videos': len(positive_videos) - stage1_found,
        }

    def training_manifest(self):
        return [{
            'test_id': row['test_id'], 'video': row['source_path'],
            'sha256': row['source_sha256'], 'ground_truth': row['actual_outcome'],
            'accident_timestamp_seconds': row['actual_timestamp'],
            'approved_for_training': row['approved_for_training'],
            'reviewer_note': row['reviewer_note'] or '',
        } for row in self.all() if row['approved_for_training']]
