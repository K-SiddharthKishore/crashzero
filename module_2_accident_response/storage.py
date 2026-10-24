"""Dedicated SQLite persistence; it never opens Module 1 stores."""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path


class AccidentRepository:
    def __init__(self, db_path):
        self.path=Path(db_path); self.lock=threading.RLock()
        with self._connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS m2_cameras (
              camera_id TEXT PRIMARY KEY, name TEXT NOT NULL, location TEXT, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS m2_incidents (
              incident_id TEXT PRIMARY KEY, created_at REAL NOT NULL, source_kind TEXT NOT NULL,
              event_offset REAL, camera_id TEXT, location TEXT, state TEXT NOT NULL, score REAL NOT NULL,
              explanation TEXT NOT NULL, reliability_json TEXT NOT NULL, track_ids_json TEXT NOT NULL,
              clip_path TEXT, screenshot_path TEXT, original_recording_time TEXT, called INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS m2_call_attempts (
              id TEXT PRIMARY KEY, incident_id TEXT, kind TEXT NOT NULL, mode TEXT NOT NULL, destination TEXT,
              message TEXT NOT NULL, status TEXT NOT NULL, provider_id TEXT, detail TEXT, created_at REAL NOT NULL,
              updated_at REAL NOT NULL, UNIQUE(incident_id, kind));
            CREATE TABLE IF NOT EXISTS m2_call_status_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT, call_id TEXT NOT NULL, status TEXT NOT NULL,
              detail TEXT, recorded_at REAL NOT NULL,
              FOREIGN KEY(call_id) REFERENCES m2_call_attempts(id));
            CREATE INDEX IF NOT EXISTS m2_call_status_idx ON m2_call_attempts(status, created_at);
            CREATE TABLE IF NOT EXISTS m2_gateway_activity (
              id INTEGER PRIMARY KEY CHECK (id=1), last_poll_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS m2_verifications (
              incident_id TEXT PRIMARY KEY, source_key TEXT NOT NULL,
              cache_key TEXT, evidence_json TEXT NOT NULL, frame_timestamps_json TEXT NOT NULL,
              evidence_limitation TEXT, status TEXT NOT NULL DEFAULT 'PENDING',
              classification TEXT, explanation TEXT, visible_evidence_json TEXT,
              limitations_json TEXT, model TEXT, input_tokens INTEGER, output_tokens INTEGER,
              estimated_usd REAL NOT NULL DEFAULT 0, attempt_count INTEGER NOT NULL DEFAULT 0,
              error TEXT, updated_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS m2_verifications_cache_idx
              ON m2_verifications(cache_key,status);
            ''')
    def _connect(self):
        db=sqlite3.connect(self.path,timeout=15)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL'); db.execute('PRAGMA foreign_keys=ON')
        return db
    def save_camera(self,camera_id,name,location):
        with self.lock,self._connect() as db:
            db.execute('INSERT INTO m2_cameras VALUES(?,?,?,?) ON CONFLICT(camera_id) DO UPDATE SET name=excluded.name,location=excluded.location,updated_at=excluded.updated_at',(camera_id,name,location,time.time()))
    def save_incident(self,row):
        with self.lock,self._connect() as db:
            db.execute('''INSERT OR IGNORE INTO m2_incidents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)''',
              (row['incident_id'],time.time(),row['source_kind'],row.get('event_offset'),row.get('camera_id'),row.get('location'),row['state'],row['score'],row['explanation'],json.dumps(row['reliability']),json.dumps(row['track_ids']),row.get('clip_path'),row.get('screenshot_path'),row.get('original_recording_time')))
            if len(row.get('evidence_paths',[])) == 2:
                db.execute('''INSERT OR IGNORE INTO m2_verifications
                    (incident_id,source_key,evidence_json,frame_timestamps_json,
                     evidence_limitation,updated_at) VALUES (?,?,?,?,?,?)''',
                    (row['incident_id'],row.get('source_key',''),
                     json.dumps(row['evidence_paths']),json.dumps(row['frame_timestamps']),
                     row.get('evidence_limitation'),time.time()))

    def verification(self, incident_id):
        with self._connect() as db:
            row=db.execute('SELECT * FROM m2_verifications WHERE incident_id=?',(incident_id,)).fetchone()
        if row is None:return None
        data=dict(row)
        for field,output in (('evidence_json','evidence_paths'),
                             ('frame_timestamps_json','frame_timestamps'),
                             ('visible_evidence_json','visible_evidence'),
                             ('limitations_json','limitations')):
            data[output]=json.loads(data.pop(field) or '[]')
        return data

    def submitted_evidence(self, incident_id):
        """Return the verified request's original JPEG pair for preview."""
        with self._connect() as db:
            row = db.execute('SELECT * FROM m2_verifications WHERE incident_id=?',
                             (incident_id,)).fetchone()
            if row is None or row['status'] != 'VERIFIED':
                return None
            if row['attempt_count'] == 0:
                row = db.execute('''SELECT * FROM m2_verifications WHERE cache_key=?
                    AND status='VERIFIED' AND attempt_count>0
                    ORDER BY updated_at ASC LIMIT 1''', (row['cache_key'],)).fetchone()
            if row is None:
                return None
            data = dict(row)
            data['evidence_paths'] = json.loads(data.pop('evidence_json'))
            data['frame_timestamps'] = json.loads(data.pop('frame_timestamps_json'))
            return data

    def verification_spending(self):
        with self._connect() as db:
            return float(db.execute('SELECT COALESCE(SUM(estimated_usd),0) FROM m2_verifications').fetchone()[0])

    def reuse_cached(self, incident_id, model):
        """Reuse an identical verified incident without a paid reservation."""
        import hashlib
        from test_lab.verification import VERIFICATION_POLICY
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM m2_verifications WHERE incident_id=?',
                             (incident_id,)).fetchone()
            if row is None or row['status'] != 'PENDING':
                return False
            cache_key = hashlib.sha256(
                f"{row['source_key']}:{json.loads(row['frame_timestamps_json'])[0]:.3f}:{model}:{VERIFICATION_POLICY}".encode()).hexdigest()
            cached = db.execute("SELECT * FROM m2_verifications WHERE cache_key=? AND status='VERIFIED' LIMIT 1",
                                (cache_key,)).fetchone()
            if cached is None:
                return False
            db.execute('''UPDATE m2_verifications SET status='VERIFIED',classification=?,explanation=?,
                visible_evidence_json=?,limitations_json=?,model=?,input_tokens=?,output_tokens=?,
                cache_key=?,error=NULL,updated_at=? WHERE incident_id=?''',
                (cached['classification'],cached['explanation'],cached['visible_evidence_json'],
                 cached['limitations_json'],cached['model'],cached['input_tokens'],
                 cached['output_tokens'],cache_key,time.time(),incident_id))
            return True

    def claim_verification(self,incident_id,config):
        from test_lab.verification import VERIFICATION_POLICY, estimated_request_cost
        import hashlib
        with self.lock,self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM m2_verifications WHERE incident_id=?',(incident_id,)).fetchone()
            if row is None:raise KeyError(incident_id)
            if row['status']=='VERIFIED' or (row['status']=='PROCESSING' and time.time()-row['updated_at']<120):
                return 'already_done'
            cache_key=hashlib.sha256(f"{row['source_key']}:{json.loads(row['frame_timestamps_json'])[0]:.3f}:{config['model']}:{VERIFICATION_POLICY}".encode()).hexdigest()
            cached=db.execute("SELECT * FROM m2_verifications WHERE cache_key=? AND status='VERIFIED' LIMIT 1",(cache_key,)).fetchone()
            if cached:
                db.execute('''UPDATE m2_verifications SET status='VERIFIED',classification=?,explanation=?,
                    visible_evidence_json=?,limitations_json=?,model=?,input_tokens=?,output_tokens=?,
                    cache_key=?,error=NULL,updated_at=? WHERE incident_id=?''',
                    (cached['classification'],cached['explanation'],cached['visible_evidence_json'],
                     cached['limitations_json'],cached['model'],cached['input_tokens'],
                     cached['output_tokens'],cache_key,time.time(),incident_id))
                return 'cached'
            attempts=db.execute('SELECT COALESCE(SUM(attempt_count),0) FROM m2_verifications WHERE source_key=?',
                                (row['source_key'],)).fetchone()[0]
            if attempts>=config['max_requests_per_video']:
                reason='Per-video request limit reached.'
            elif self.verification_spending()+estimated_request_cost(config)>config['budget_usd']:
                reason='Session budget exhausted.'
            else:reason=None
            if reason:
                db.execute("UPDATE m2_verifications SET status='VERIFICATION_FAILED',error=?,updated_at=? WHERE incident_id=?",
                           (reason,time.time(),incident_id))
                return 'limited'
            db.execute('''UPDATE m2_verifications SET status='PROCESSING',cache_key=?,model=?,
                estimated_usd=estimated_usd+?,attempt_count=attempt_count+1,error=NULL,updated_at=?
                WHERE incident_id=?''',(cache_key,config['model'],estimated_request_cost(config),time.time(),incident_id))
            return 'claimed'

    def finish_verification(self,incident_id,result,config):
        from test_lab.verification import cost_usd, estimated_request_cost
        input_tokens=result.get('input_tokens');output_tokens=result.get('output_tokens')
        actual=(cost_usd(input_tokens,output_tokens,config)
                if input_tokens is not None and output_tokens is not None
                else estimated_request_cost(config))
        with self.lock,self._connect() as db:
            db.execute('''UPDATE m2_verifications SET status='VERIFIED',classification=?,explanation=?,
                visible_evidence_json=?,limitations_json=?,input_tokens=?,output_tokens=?,
                estimated_usd=estimated_usd-?+?,error=NULL,updated_at=? WHERE incident_id=?''',
                (result['classification'],result['explanation'],json.dumps(result['visible_evidence']),
                 json.dumps(result['limitations']),input_tokens,output_tokens,
                 estimated_request_cost(config),actual,time.time(),incident_id))

    def fail_verification(self,incident_id,message='Verification request failed or returned invalid data.'):
        with self.lock,self._connect() as db:
            db.execute("UPDATE m2_verifications SET status='VERIFICATION_FAILED',error=?,updated_at=? WHERE incident_id=?",
                       (message,time.time(),incident_id))
    def incidents(self):
        with self._connect() as db:
            return [dict(r)|{'reliability':json.loads(r['reliability_json']),'track_ids':json.loads(r['track_ids_json'])} for r in db.execute('SELECT * FROM m2_incidents ORDER BY created_at DESC')]
    def call(self,row):
        with self.lock,self._connect() as db:
            previous=db.execute('SELECT status FROM m2_call_attempts WHERE id=?',(row['id'],)).fetchone()
            db.execute('''INSERT INTO m2_call_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status,provider_id=excluded.provider_id,
                detail=excluded.detail,updated_at=excluded.updated_at''',
                (row['id'],row.get('incident_id'),row['kind'],row['mode'],row.get('destination'),row['message'],row['status'],row.get('provider_id'),row.get('detail'),time.time(),time.time()))
            if previous is None or previous['status']!=row['status']:
                db.execute('INSERT INTO m2_call_status_history(call_id,status,detail,recorded_at) VALUES(?,?,?,?)',
                    (row['id'],row['status'],row.get('detail'),time.time()))
    def call_by_incident(self,incident_id,kind='automatic'):
        with self._connect() as db:
            row=db.execute('SELECT * FROM m2_call_attempts WHERE incident_id=? AND kind=?',(incident_id,kind)).fetchone()
            return dict(row) if row else None
    def call_by_id(self,identity):
        with self._connect() as db:
            row=db.execute('SELECT * FROM m2_call_attempts WHERE id=?',(identity,)).fetchone()
            return dict(row) if row else None
    def update_call_status(self,identity,status,detail=None,provider_id=None):
        row=self.call_by_id(identity)
        if not row:return None
        row.update(status=status,detail=detail,provider_id=provider_id or row.get('provider_id'))
        self.call(row);return self.call_by_id(identity)
    def requeue_call(self,identity):
        with self.lock,self._connect() as db:
            now=time.time()
            changed=db.execute('''UPDATE m2_call_attempts SET status='QUEUED',detail=NULL,
                created_at=?,updated_at=? WHERE id=? AND mode='android_gateway'
                AND status IN ('WITHHELD','EXPIRED')''',(now,now,identity)).rowcount
            if not changed:return None
            db.execute('INSERT INTO m2_call_status_history(call_id,status,detail,recorded_at) VALUES(?,?,?,?)',
                (identity,'QUEUED','Retried after a withheld or expired request',now))
            return dict(db.execute('SELECT * FROM m2_call_attempts WHERE id=?',(identity,)).fetchone())
    def next_gateway_call(self):
        with self.lock,self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            now=time.time()
            ttl=max(30,int(os.getenv('M2_GATEWAY_QUEUE_TTL_SECONDS','120')))
            expired=db.execute("SELECT id FROM m2_call_attempts WHERE mode='android_gateway' AND status='QUEUED' AND created_at<?",(now-ttl,)).fetchall()
            for old in expired:
                db.execute("UPDATE m2_call_attempts SET status='EXPIRED',detail='Android gateway did not collect the call in time',updated_at=? WHERE id=?",(now,old['id']))
                db.execute("INSERT INTO m2_call_status_history(call_id,status,detail,recorded_at) VALUES(?,?,?,?)",
                    (old['id'],'EXPIRED','Android gateway did not collect the call in time',now))
            db.execute('INSERT INTO m2_gateway_activity(id,last_poll_at) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET last_poll_at=excluded.last_poll_at',(now,))
            row=db.execute('''SELECT c.*, i.camera_id, cam.name AS camera_name, i.location, i.state AS event_type,
                i.created_at AS event_timestamp FROM m2_call_attempts c
                LEFT JOIN m2_incidents i ON i.incident_id=c.incident_id
                LEFT JOIN m2_cameras cam ON cam.camera_id=i.camera_id
                WHERE c.mode='android_gateway' AND c.status='QUEUED'
                ORDER BY c.created_at ASC LIMIT 1''').fetchone()
            if not row:return None
            db.execute("UPDATE m2_call_attempts SET status='RECEIVED',detail='Claimed by Android gateway',updated_at=? WHERE id=? AND status='QUEUED'",(time.time(),row['id']))
            db.execute("INSERT INTO m2_call_status_history(call_id,status,detail,recorded_at) VALUES(?,?,?,?)",(row['id'],'RECEIVED','Claimed by Android gateway',time.time()))
            return dict(row)|{'status':'RECEIVED','detail':'Claimed by Android gateway'}
    def last_gateway_poll(self):
        with self._connect() as db:
            row=db.execute('SELECT last_poll_at FROM m2_gateway_activity WHERE id=1').fetchone()
            return row['last_poll_at'] if row else None
    def status_history(self,identity):
        with self._connect() as db:
            return [dict(r) for r in db.execute('SELECT status,detail,recorded_at FROM m2_call_status_history WHERE call_id=? ORDER BY id',(identity,))]
    def calls(self):
        with self._connect() as db:return [dict(r) for r in db.execute('SELECT * FROM m2_call_attempts ORDER BY created_at DESC')]
