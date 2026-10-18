"""Durable at-most-one automatic submission, independent of UI/evidence updates."""
from pathlib import Path
import hashlib
import json
import sqlite3
import time
import uuid


def recorded_key(incident):
    # Stable across replay, filenames and tracking IDs. Media digest is generated
    # by the analysis worker; legacy records cannot receive real auto calls.
    if incident.get('source_kind') != 'live camera':
        digest = incident.get('media_digest')
        if not digest: return None
        # Region/time are checked with tolerances transactionally, not only buckets.
        return 'recorded:'+digest
    return 'live:'+incident.get('camera_id','')


class CallStore:
    def __init__(self, root):
        self.root = Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.db = self.root/'calls.sqlite'
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS attempts (
              id TEXT PRIMARY KEY, incident_id TEXT, provider TEXT, destination TEXT,
              requested_at REAL, provider_call_id TEXT, status TEXT, kind TEXT,
              event_key TEXT, event_time REAL, x REAL, y REAL, detail TEXT,
              token TEXT UNIQUE, message TEXT, reset_at REAL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_auto_incident ON attempts(incident_id)
              WHERE kind='automatic' AND reset_at IS NULL;
            CREATE TABLE IF NOT EXISTS eligibility (incident_id TEXT PRIMARY KEY, payload TEXT);
            CREATE TABLE IF NOT EXISTS acknowledgements (configuration TEXT PRIMARY KEY, attempt_id TEXT);
            CREATE TABLE IF NOT EXISTS audit (created_at REAL, action TEXT, subject TEXT);
            ''')

    def connect(self):
        db=sqlite3.connect(self.db,timeout=10)
        db.row_factory=sqlite3.Row
        return db

    def eligibility(self, incident_id, result=None):
        with self.connect() as db:
            if result is not None:
                db.execute('INSERT OR REPLACE INTO eligibility VALUES (?,?)',(incident_id,json.dumps(result)))
                return result
            row=db.execute('SELECT payload FROM eligibility WHERE incident_id=?',(incident_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def reserve(self, incident, provider, destination, kind, message, real=False):
        now=time.time(); event_key=recorded_key(incident)
        event_time=incident.get('timestamp',0.)
        if incident.get('source_kind')=='live camera':
            from datetime import datetime
            event_time=datetime.fromisoformat(incident['observed_at']).timestamp()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if real:
                count=db.execute("SELECT count(*) FROM attempts WHERE provider!='mock' AND requested_at>?",(now-86400,)).fetchone()[0]
                recent=db.execute("SELECT count(*) FROM attempts WHERE provider!='mock' AND requested_at>?",(now-60,)).fetchone()[0]
                if count>=5 or recent: return None,'Real-call rate limit reached.'
            if real and kind=='automatic':
                if not event_key: return None,'Stable source identity unavailable.'
                rows=db.execute("SELECT * FROM attempts WHERE event_key=? AND kind='automatic' AND provider!='mock' AND reset_at IS NULL",(event_key,)).fetchall()
                for row in rows:
                    if abs(row['event_time']-event_time)<=12 and ((row['x']-incident.get('x',0))**2+(row['y']-incident.get('y',0))**2)**.5<=100:
                        return None,'This recorded/live event already has a real call reservation.'
            identity=uuid.uuid4().hex; token=uuid.uuid4().hex+uuid.uuid4().hex
            try:
                db.execute('INSERT INTO attempts (id,incident_id,provider,destination,requested_at,status,kind,event_key,event_time,x,y,token,message) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (identity,incident['incident_id'],provider,destination,now,'RESERVED',kind,event_key,event_time,incident.get('x',0),incident.get('y',0),token,message))
            except sqlite3.IntegrityError: return None,'Incident already reserved.'
            return identity,None

    def update(self, identity, status, provider_id=None, detail=None):
        with self.connect() as db:
            db.execute("UPDATE attempts SET status=CASE WHEN status IN ('COMPLETED','FAILED') THEN status ELSE ? END,provider_call_id=COALESCE(?,provider_call_id),detail=? WHERE id=?",
                       (status,provider_id,detail,identity))

    def get(self, identity):
        with self.connect() as db:
            row=db.execute('SELECT * FROM attempts WHERE id=?',(identity,)).fetchone()
            return dict(row) if row else None

    def by_token(self, token):
        with self.connect() as db:
            row=db.execute('SELECT * FROM attempts WHERE token=? AND requested_at>?',(token,time.time()-3600)).fetchone()
            return dict(row) if row else None

    def list(self, incident_id=None):
        with self.connect() as db:
            if incident_id: rows=db.execute('SELECT * FROM attempts WHERE incident_id=? ORDER BY requested_at DESC',(incident_id,)).fetchall()
            else: rows=db.execute('SELECT * FROM attempts ORDER BY requested_at DESC LIMIT 100').fetchall()
            return [dict(row) for row in rows]

    def acknowledge(self, configuration, identity):
        row=self.get(identity)
        if not row or row['kind']!='manual' or row['status']!='COMPLETED':
            raise ValueError('A completed manual test is required.')
        from .config import CallConfig
        config=CallConfig.load()
        from .service import configuration_key
        if configuration!=configuration_key(config): raise ValueError('Configuration changed.')
        if row['provider']!=config.provider or row['destination']!=config.destination:
            raise ValueError('Manual test belongs to a different provider/destination.')
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO acknowledgements VALUES (?,?)',(configuration,identity))

    def acknowledged(self, configuration):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM acknowledgements WHERE configuration=?',(configuration,)).fetchone() is not None

    def reset(self, identity, confirmation):
        if confirmation != 'AUTHORIZE ANOTHER REAL TEST CALL': raise ValueError('Explicit reset authorization required.')
        with self.connect() as db:
            db.execute('UPDATE attempts SET reset_at=? WHERE id=?',(time.time(),identity))
            db.execute('INSERT INTO audit VALUES (?,?,?)',(time.time(),'authorized real-call reset',identity))
