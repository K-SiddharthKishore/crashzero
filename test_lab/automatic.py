"""Automatic verification with a shared, durable spending reservation."""
import os
import json
import sqlite3
import time
from pathlib import Path

from .verification import VERIFICATION_POLICY, cost_usd, safe_failure, settings, verify_pair


def _audit(root, kind, identity, record, classification, reason):
    """Keep the actual model decision server-side, outside the simple UI."""
    entry = {'recorded_at': time.time(), 'kind': kind, 'event_id': identity,
             'classification': classification, 'reason': reason,
             'stage1_timestamp': record.get('timestamp', record.get('frame_timestamps', [None])[0]),
             'frame_timestamps': record.get('frame_timestamps'),
             'verification_policy': VERIFICATION_POLICY}
    try:
        with (Path(root) / 'verification_audit.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except OSError:
        pass  # The SQLite record remains authoritative if an auxiliary log is unavailable.


class SessionBudget:
    """One app-wide cap across TEST and Module 2, including in-flight requests."""

    def __init__(self, root):
        self.path = Path(root) / 'openai_budget.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            existed = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reservations'").fetchone()
            db.execute('''CREATE TABLE IF NOT EXISTS reservations (
                request_key TEXT PRIMARY KEY, usd REAL NOT NULL, created_at REAL NOT NULL)''')
            if not existed:
                previous = 0.0
                for relative, table in (('test_lab/test_history.sqlite3','test_events'),
                                        ('module2_accident_response/module2.sqlite3','m2_verifications')):
                    source = self.path.parent / relative
                    if source.exists():
                        try:
                            with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as old:
                                previous += float(old.execute(
                                    f'SELECT COALESCE(SUM(estimated_usd),0) FROM {table}').fetchone()[0])
                        except sqlite3.Error:
                            pass
                if previous:
                    db.execute('INSERT INTO reservations VALUES (?,?,?)',
                               ('prior-local-usage', previous, time.time()))

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute('PRAGMA journal_mode=WAL')
        return db

    def reserve(self, request_key, config):
        # Two bounded 1024-pixel JPEGs are far below this token ceiling. Keep
        # the reserve intentionally larger than the expected bill.
        input_ceiling = max(config['estimated_input_tokens'],
                            int(os.getenv('OPENAI_BUDGET_RESERVE_INPUT_TOKENS', '100000')))
        amount = cost_usd(input_ceiling, max(1200, config['estimated_output_tokens']), config)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM reservations WHERE request_key=?',
                          (request_key,)).fetchone():
                return False
            spent = db.execute('SELECT COALESCE(SUM(usd),0) FROM reservations').fetchone()[0]
            if spent + amount > config['budget_usd']:
                return False
            db.execute('INSERT INTO reservations VALUES (?,?,?)',
                       (request_key, amount, time.time()))
            return True

    def release(self, request_key):
        with self._connect() as db:
            db.execute('DELETE FROM reservations WHERE request_key=?', (request_key,))

    def settle(self, request_key, result, config):
        if result.get('input_tokens') is None or result.get('output_tokens') is None:
            return  # Keep the conservative reservation when usage is unavailable.
        actual = cost_usd(result['input_tokens'], result['output_tokens'], config)
        with self._connect() as db:
            db.execute('UPDATE reservations SET usd=? WHERE request_key=?',
                       (actual, request_key))

    def spent(self):
        with self._connect() as db:
            return float(db.execute('SELECT COALESCE(SUM(usd),0) FROM reservations').fetchone()[0])


def _effective_budget_root(root):
    """Share one paid-request ledger across hosted visitors on this server."""
    if os.getenv('CRASHZERO_V2_HOSTED') == '1':
        return Path(os.getenv('CRASHZERO_SHARED_BUDGET_DIR',
                              str(Path(__file__).resolve().parents[1] /
                                  'outputs' / 'cloud_verification_budget')))
    return Path(root)


def run_automatic_verification(store, identity, *, kind, budget_root, client=None):
    """Make at most one request for a pending candidate; never auto-retry failures."""
    record = store.event(identity) if kind == 'test' else store.verification(identity)
    if not record or record['status'] != 'PENDING':
        return record
    if len(record['evidence_paths']) != 2:
        store.fail_verification(identity, 'Two evidence frames are unavailable.')
        return store.event(identity) if kind == 'test' else store.verification(identity)
    config = settings()
    if store.reuse_cached(identity, config['model']):
        return store.event(identity) if kind == 'test' else store.verification(identity)
    if client is None and not os.getenv('OPENAI_API_KEY'):
        store.fail_verification(identity, 'OpenAI verification is unavailable.')
        return store.event(identity) if kind == 'test' else store.verification(identity)
    budget = SessionBudget(_effective_budget_root(budget_root))
    request_key = f'{kind}:{identity}'
    if not budget.reserve(request_key, config):
        store.fail_verification(identity, 'Verification budget exhausted or request already reserved.')
        return store.event(identity) if kind == 'test' else store.verification(identity)
    try:
        claim = store.claim_verification(identity, config)
    except Exception as exc:
        budget.release(request_key)
        store.fail_verification(identity, safe_failure(exc))
        return store.event(identity) if kind == 'test' else store.verification(identity)
    if claim != 'claimed':
        budget.release(request_key)
        return store.event(identity) if kind == 'test' else store.verification(identity)
    try:
        result = verify_pair(record['evidence_paths'], config['model'], client=client)
        store.finish_verification(identity, result, config)
        budget.settle(request_key, result, config)
        _audit(budget_root, kind, identity, record, result['classification'], result['explanation'])
    except Exception as exc:
        reason = safe_failure(exc)
        store.fail_verification(identity, reason)
        _audit(budget_root, kind, identity, record, 'VERIFICATION_FAILED', reason)
    return store.event(identity) if kind == 'test' else store.verification(identity)


def alert_state(records, *, analyzing=False):
    """Only a completed OpenAI negative finding can produce GREEN."""
    if any(row and row.get('classification') == 'LIKELY_ACCIDENT'
           and row.get('status') == 'VERIFIED' for row in records):
        return 'ALERT', None
    if any(row and row.get('status') == 'VERIFICATION_FAILED' for row in records):
        if any('budget' in (row.get('error') or '').lower() for row in records):
            return 'VERIFICATION UNAVAILABLE', 'Verification budget exhausted.'
        return 'VERIFICATION UNAVAILABLE', 'Stage 2 verification unavailable.'
    if any(row and row.get('status') in ('PROCESSING', 'PENDING') for row in records):
        return 'ANALYZING', 'Verifying suspicious event.'
    if analyzing:
        return 'ANALYZING', 'Analyzing video.'
    if any(row and row.get('status') == 'VERIFIED' and
           row.get('classification') == 'UNCERTAIN' for row in records):
        return 'REVIEW', 'Evidence requires review.'
    if records and all(row and row.get('status') == 'VERIFIED' and
                       row.get('classification') == 'NO_ACCIDENT_EVIDENCE' for row in records):
        return 'NO ALERT', None
    if records:
        return 'VERIFICATION UNAVAILABLE', 'Verification result unavailable.'
    return 'NO SUSPICIOUS EVENT DETECTED', None
