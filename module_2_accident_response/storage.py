"""Dedicated SQLite persistence; it never opens Module 1 stores."""
import json
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
    def next_gateway_call(self):
        with self.lock,self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
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
    def status_history(self,identity):
        with self._connect() as db:
            return [dict(r) for r in db.execute('SELECT status,detail,recorded_at FROM m2_call_status_history WHERE call_id=? ORDER BY id',(identity,))]
    def recent_real_calls(self,since):
        with self._connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM m2_call_attempts WHERE mode='android_gateway' AND created_at>=? AND status!='WITHHELD' ORDER BY created_at DESC",(since,))]
    def calls(self):
        with self._connect() as db:return [dict(r) for r in db.execute('SELECT * FROM m2_call_attempts ORDER BY created_at DESC')]
