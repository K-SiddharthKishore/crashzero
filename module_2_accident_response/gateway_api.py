"""Authenticated LAN polling API for the CrashZero Android calling gateway."""
import hmac
import os
import time
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from .config import Module2Config
from .storage import AccidentRepository

app=FastAPI(title='CrashZero Android Gateway',docs_url=None,redoc_url=None)
repo=AccidentRepository(Module2Config.load().db_path)
ALLOWED_STATUSES={'RECEIVED','DIALING_REQUESTED','REQUIRES_CONFIRMATION','CALL_ACTIVE','CALL_ENDED','FAILED'}

@app.get('/')
def landing():
    return {'service':'CrashZero Android Gateway','status':'running',
            'next_step':'Enter this address in the Android app Server URL field, then tap Test Connection.'}

class StatusUpdate(BaseModel):
    status: str
    detail: str|None=Field(default=None,max_length=300)

def authenticate(authorization):
    expected=os.getenv('M2_GATEWAY_TOKEN','')
    supplied=authorization.removeprefix('Bearer ').strip() if authorization else ''
    if len(expected)<32 or not hmac.compare_digest(supplied,expected):raise HTTPException(401,'Invalid gateway token.')
    if os.getenv('M2_REAL_CALLS_ENABLED','false').lower()!='true' or os.getenv('M2_CALL_KILL_SWITCH','true').lower()=='true':
        raise HTTPException(503,'Android gateway calling is disabled.')

@app.get('/api/v1/health')
def health(authorization: str|None=Header(default=None)):
    authenticate(authorization);return {'status':'ready','server_time':time.time()}

@app.get('/api/v1/calls/next')
def next_call(authorization: str|None=Header(default=None)):
    authenticate(authorization);row=repo.next_gateway_call()
    if not row:return {'call':None,'server_time':time.time()}
    return {'call':{'id':row['id'],'incident_id':row['incident_id'],'kind':row['kind'],
        'destination':row['destination'],'message':row['message'],'camera_id':row.get('camera_id'),
        'camera_name':row.get('camera_name'),
        'location':row.get('location'),'event_type':row.get('event_type'),
        'event_timestamp':row.get('event_timestamp'),'created_at':row['created_at']},'server_time':time.time()}

@app.post('/api/v1/calls/{identity}/status')
def update_status(identity: str, update: StatusUpdate, authorization: str|None=Header(default=None)):
    authenticate(authorization);status=update.status.upper()
    if status not in ALLOWED_STATUSES:raise HTTPException(422,'Unsupported call status.')
    current=repo.call_by_id(identity)
    if not current or current['mode']!='android_gateway':raise HTTPException(404,'Call request not found.')
    row=repo.update_call_status(identity,status,update.detail)
    return {'id':identity,'status':row['status'],'updated_at':row['updated_at']}

@app.get('/api/v1/calls/{identity}')
def call_status(identity: str, authorization: str|None=Header(default=None)):
    authenticate(authorization);row=repo.call_by_id(identity)
    if not row:raise HTTPException(404,'Call request not found.')
    return {'id':identity,'status':row['status'],'detail':row['detail'],'history':repo.status_history(identity)}
