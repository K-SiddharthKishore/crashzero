"""Callback-only HTTP app: no call-creation endpoint and no dashboard exposure."""
import os
from urllib.parse import parse_qsl
from xml.sax.saxutils import escape
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
from config.settings import ROOT
from .store import CallStore
from .providers import normalize_status


def create_app(store=None):
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    ledger=store or CallStore(ROOT/'outputs/calls')

    @app.get('/health')
    def health(): return {'status':'ok','purpose':'test-call callbacks only'}

    async def plivo_request(request, token):
        import plivo
        raw=await request.body()
        if len(raw)>16384: raise HTTPException(413)
        params=dict(parse_qsl(raw.decode(),keep_blank_values=True))
        signature=request.headers.get('X-Plivo-Signature-V3','')
        nonce=request.headers.get('X-Plivo-Signature-V3-Nonce','')
        auth=os.getenv('PLIVO_AUTH_TOKEN','')
        base=os.getenv('CALLBACK_BASE_URL','').rstrip('/')
        url=base+request.url.path
        if request.url.query: url+='?'+request.url.query
        if not auth or not base.startswith('https://') or not signature or not nonce:
            raise HTTPException(403)
        if not plivo.utils.validate_v3_signature(request.method,url,nonce,auth,signature,params):
            raise HTTPException(403)
        row=ledger.by_token(token)
        if not row or row['provider']!='plivo': raise HTTPException(404)
        return row,params

    @app.post('/plivo/answer/{token}')
    async def answer(token: str, request: Request):
        row,params=await plivo_request(request,token)
        ledger.update(row['id'],'ANSWERED',params.get('CallUUID'))
        enabled=os.getenv('REAL_CALLS_ENABLED','false').lower()=='true'
        xml='<Response><Speak>'+escape(row['message'])+'</Speak><Hangup/></Response>' if enabled else '<Response><Hangup/></Response>'
        return Response(xml,media_type='application/xml')

    @app.post('/plivo/status/{token}')
    async def status(token: str, request: Request):
        row,params=await plivo_request(request,token)
        state=normalize_status(params.get('CallStatus','unknown'))
        if state!='UNKNOWN': ledger.update(row['id'],state,params.get('CallUUID'))
        return {'received':True}

    @app.api_route('/exotel/greeting',methods=['GET','HEAD'])
    async def greeting(request: Request):
        row=ledger.by_token(request.query_params.get('CustomField',''))
        call_id=request.query_params.get('CallSid','')
        if (not row or row['provider']!='exotel' or not call_id
            or row['provider_call_id']!=call_id): raise HTTPException(403)
        text=row['message'] if os.getenv('REAL_CALLS_ENABLED','false').lower()=='true' else 'Test notification disabled.'
        return Response('' if request.method=='HEAD' else text,headers={'Content-Type':'text/plain','Cache-Control':'no-store'})

    return app

app=create_app()
