from module_2_accident_response.config import Module2Config
from module_2_accident_response.storage import AccidentRepository
from module_2_accident_response.alerts import CallService
from fastapi.testclient import TestClient

def test_module2_uses_its_own_database(tmp_path):
    cfg=Module2Config.load(tmp_path); assert cfg.db_path.name=='module2.sqlite3'
    repo=AccidentRepository(cfg.db_path);repo.save_incident({'incident_id':'CZ-AR-TEST','source_kind':'uploaded video','state':'UNCERTAIN','score':.2,'explanation':'x','reliability':{},'track_ids':[]})
    assert repo.incidents()[0]['incident_id']=='CZ-AR-TEST'

def test_mock_call_needs_allowlisted_consent(tmp_path,monkeypatch):
    repo=AccidentRepository(tmp_path/'m2.sqlite3');service=CallService(repo)
    monkeypatch.setenv('M2_APPROVED_TEST_PHONE','+919999999999');monkeypatch.setenv('M2_TEST_PHONE_CONSENT','true');monkeypatch.setenv('M2_CALL_MODE','mock')
    row=service.submit(test=True);assert row['status']=='SIMULATED';assert repo.calls()[0]['mode']=='mock'

def test_emergency_numbers_are_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv('M2_APPROVED_TEST_PHONE','112');monkeypatch.setenv('M2_TEST_PHONE_CONSENT','true')
    assert CallService(AccidentRepository(tmp_path/'m2.sqlite3')).submit(test=True)['status']=='WITHHELD'

def test_real_call_queues_for_android_and_deduplicates(tmp_path,monkeypatch):
    repo=AccidentRepository(tmp_path/'m2.sqlite3');service=CallService(repo)
    for key,value in {'M2_CALL_MODE':'real','M2_CALL_PROVIDER':'android_gateway','M2_REAL_CALLS_ENABLED':'true',
        'M2_CALL_KILL_SWITCH':'false','M2_APPROVED_TEST_PHONE':'+919999999999','M2_TEST_PHONE_CONSENT':'true',
        'M2_GATEWAY_TOKEN':'z'*32}.items():monkeypatch.setenv(key,value)
    incident={'incident_id':'CZ-AR-ONE','source_kind':'uploaded video','location':'Test junction'}
    first=service.submit(incident);second=service.submit(incident)
    assert first['status']=='QUEUED' and second['id']==first['id'] and len(repo.calls())==1

def test_gateway_authenticated_poll_and_status(tmp_path,monkeypatch):
    import module_2_accident_response.gateway_api as api
    repo=AccidentRepository(tmp_path/'m2.sqlite3');monkeypatch.setattr(api,'repo',repo)
    monkeypatch.setenv('M2_GATEWAY_TOKEN','x'*32);monkeypatch.setenv('M2_REAL_CALLS_ENABLED','true');monkeypatch.setenv('M2_CALL_KILL_SWITCH','false')
    repo.call({'id':'m2-call-one','incident_id':None,'kind':'test','mode':'android_gateway','destination':'+919999999999','message':'test','status':'QUEUED'})
    client=TestClient(api.app);headers={'Authorization':'Bearer '+'x'*32}
    assert client.get('/api/v1/calls/next').status_code==401
    found=client.get('/api/v1/calls/next',headers=headers).json()['call'];assert found['id']=='m2-call-one'
    changed=client.post('/api/v1/calls/m2-call-one/status',headers=headers,json={'status':'RECEIVED'});assert changed.json()['status']=='RECEIVED'
    assert [x['status'] for x in repo.status_history('m2-call-one')]==['QUEUED','RECEIVED']

def test_gateway_kill_switch_blocks_poll(tmp_path,monkeypatch):
    import module_2_accident_response.gateway_api as api
    monkeypatch.setattr(api,'repo',AccidentRepository(tmp_path/'m2.sqlite3'));monkeypatch.setenv('M2_GATEWAY_TOKEN','y'*32)
    monkeypatch.setenv('M2_REAL_CALLS_ENABLED','true');monkeypatch.setenv('M2_CALL_KILL_SWITCH','true')
    assert TestClient(api.app).get('/api/v1/calls/next',headers={'Authorization':'Bearer '+'y'*32}).status_code==503
