"""Persistence for offline TEST runs; no Module 1/2 tables are touched."""
import json
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
            ''')

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

    def all(self):
        with self._connect() as db:
            return [self._decode(row) for row in db.execute(
                'SELECT * FROM test_runs ORDER BY created_at DESC')]

    def get(self, test_id):
        with self._connect() as db:
            return self._decode(db.execute(
                'SELECT * FROM test_runs WHERE test_id=?', (test_id,)).fetchone())

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
        return {
            'total': len(rows),
            'accidents': sum(row['result'] == 'Accident Detected' for row in rows),
            'uncertain': sum(row['result'] == 'Uncertain' for row in rows),
            'verified': len(verified),
            'correct': sum(row['review'] == 'CORRECT' for row in verified),
            'accuracy': (sum(row['review'] == 'CORRECT' for row in verified) / len(verified)
                         if verified else None),
        }

    def training_manifest(self):
        return [{
            'test_id': row['test_id'], 'video': row['source_path'],
            'sha256': row['source_sha256'], 'ground_truth': row['actual_outcome'],
            'accident_timestamp_seconds': row['actual_timestamp'],
            'approved_for_training': row['approved_for_training'],
            'reviewer_note': row['reviewer_note'] or '',
        } for row in self.all() if row['approved_for_training']]
