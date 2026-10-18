import pytest
from fastapi.testclient import TestClient
from plivo.utils import signature_v3 as utils
from src.alerts.callbacks import create_app
from src.alerts.store import CallStore


def test_callback_server_exposes_no_submission_routes_and_rejects_forgery(tmp_path):
    client=TestClient(create_app(CallStore(tmp_path)))
    assert client.post('/calls',json={'to':'anything'}).status_code==404
    assert client.post('/plivo/answer/forged').status_code==403
    assert client.get('/exotel/greeting?CustomField=forged&CallSid=anything').status_code==403


def test_plivo_validated_callback_and_xml_escaping(tmp_path,monkeypatch):
    monkeypatch.setenv('PLIVO_AUTH_TOKEN','test-secret')
    monkeypatch.setenv('CALLBACK_BASE_URL','https://callback.example')
    monkeypatch.setenv('REAL_CALLS_ENABLED','true')
    store=CallStore(tmp_path)
    identity,_=store.reserve({'incident_id':'test'},'plivo','test','manual','Test <camera> & location')
    token=store.get(identity)['token'];path='/plivo/answer/'+token
    params={'CallUUID':'call-id'};nonce='test-nonce'
    url=utils.construct_post_url('https://callback.example'+path,params).decode()
    signature=utils.get_signature_v3(b'test-secret',url,nonce.encode()).decode()
    response=TestClient(create_app(store)).post(path,data=params,headers={
        'X-Plivo-Signature-V3':signature,'X-Plivo-Signature-V3-Nonce':nonce})
    assert response.status_code==200
    assert '&lt;camera&gt; &amp;' in response.text
    assert store.get(identity)['status']=='ANSWERED'
    assert store.get(identity)['provider_call_id']=='call-id'


def test_exotel_dynamic_greeting_requires_matching_call_and_supports_head(tmp_path,monkeypatch):
    monkeypatch.setenv('REAL_CALLS_ENABLED','true')
    store=CallStore(tmp_path);identity,_=store.reserve({'incident_id':'test'},'exotel','test','manual','Only a test.')
    token=store.get(identity)['token'];store.update(identity,'INITIATED','call-id')
    client=TestClient(create_app(store));url='/exotel/greeting?CustomField='+token+'&CallSid=call-id'
    assert client.get(url).text=='Only a test.'
    assert client.head(url).headers['content-type']=='text/plain'
    assert client.get(url.replace('call-id','wrong')).status_code==403
