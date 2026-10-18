import concurrent.futures
import json
import os
import pytest
from src.alerts.config import CallConfig, CallsDisabled, real_guard
from src.alerts.service import AlertService, CallEligibilityGate, configuration_key, validation_reason
from src.alerts.store import CallStore
from src.alerts.providers import MockCallProvider, PlivoCallProvider, ExotelCallProvider


@pytest.fixture(autouse=True)
def call_defaults(monkeypatch):
    for key in list(os.environ):
        if key.startswith(('CALL_','PLIVO_','EXOTEL_','TEST_PHONE_','REAL_CALLS','AUTO_TEST','CRASHZERO_LOCAL_CALLS')):
            monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('CALL_PROVIDER','mock')
    monkeypatch.setenv('REAL_CALLS_ENABLED','false')
    monkeypatch.setenv('AUTO_TEST_CALL_ENABLED','false')


def incident(identity='inc-1'):
    return {'incident_id':identity,'phase':'LIKELY_ACCIDENT','evidence_groups':{'INTERACTION':True,'IMPACT':True,'AFTERMATH':True},
        'temporal_coverage':True,'camera_motion_safe':True,'minimum_tracking_confidence':.95,
        'evidence_status':'EVIDENCE SAVED','source_kind':'video','media_digest':'same-media',
        'timestamp':10.,'x':120.,'y':140.,'camera_id':'TEST','registered_location':'Lab'}


@pytest.mark.parametrize('provider',['plivo','exotel'])
@pytest.mark.parametrize('flag',['false','true'])
def test_provider_boundary_forces_no_calls_in_tests(monkeypatch,provider,flag):
    monkeypatch.setenv('REAL_CALLS_ENABLED',flag)
    monkeypatch.setenv('CRASHZERO_LOCAL_CALLS','true')
    with pytest.raises(CallsDisabled):
        (PlivoCallProvider() if provider=='plivo' else ExotelCallProvider()).submit({'destination':'+919000000000'})


def test_missing_configuration_does_not_crash(monkeypatch):
    monkeypatch.setenv('CALL_PROVIDER','exotel')
    config=CallConfig.load()
    assert not config.allowed and 'EXOTEL_API_TOKEN' in config.missing
    assert 'configuration incomplete' in config.reason


def test_manual_mock_is_independent_of_accident_engine(tmp_path):
    service=AlertService(tmp_path)
    result=service.manual().result(timeout=5)
    assert result['status']=='COMPLETED'
    row=service.store.get(result['id'])
    assert row['kind']=='manual' and 'only a test' in row['message']


@pytest.mark.parametrize('phase',['NORMAL','NEAR_MISS','CANDIDATE','VERIFYING','UNCERTAIN'])
def test_non_accidents_never_call(tmp_path,monkeypatch,phase):
    monkeypatch.setenv('AUTO_TEST_CALL_ENABLED','true')
    service=AlertService(tmp_path); event=incident();event['phase']=phase
    assert service.automatic(event).result(timeout=5)['status']=='WITHHELD'
    assert not service.store.list()


@pytest.mark.parametrize('change',[{'camera_motion_safe':False},{'temporal_coverage':False},
    {'post_event_truncated':True},{'minimum_tracking_confidence':.2},{'evidence_groups':{'IMPACT':True}}])
def test_stricter_gate_withholds_weak_evidence(tmp_path,monkeypatch,change):
    monkeypatch.setenv('AUTO_TEST_CALL_ENABLED','true')
    event=incident();event.update(change)
    assert not CallEligibilityGate().evaluate(event,CallConfig.load(),CallStore(tmp_path))['passed']


def test_one_mock_attempt_concurrent_and_after_restart(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTO_TEST_CALL_ENABLED','true')
    service=AlertService(tmp_path)
    futures=[service.automatic(incident()) for _ in range(10)]
    results=[f.result(timeout=10) for f in futures]
    assert sum(r['status']=='COMPLETED' for r in results)==1
    assert AlertService(tmp_path).automatic(incident()).result(timeout=5)['status']=='WITHHELD'
    # New analysis gets a fresh test incident, even for identical recorded media.
    assert service.automatic(incident('replay')).result(timeout=5)['status']=='COMPLETED'


def test_real_ledger_replay_dedup_and_explicit_reset(tmp_path):
    store=CallStore(tmp_path)
    first,_=store.reserve(incident(),'plivo','configured','automatic','test',real=True)
    # Remove rate-limit time from the equation without changing event identity.
    with store.connect() as db: db.execute('UPDATE attempts SET requested_at=0')
    second,reason=store.reserve(incident('replay'),'exotel','configured','automatic','test',real=True)
    assert second is None and 'already' in reason
    with pytest.raises(ValueError): store.reset(first,'yes')
    store.reset(first,'AUTHORIZE ANOTHER REAL TEST CALL')
    assert store.reserve(incident('replay'),'exotel','configured','automatic','test',real=True)[0]


def test_ambiguous_provider_failure_preserves_attempt_and_never_retries(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTO_TEST_CALL_ENABLED','true')
    class Broken(MockCallProvider):
        calls=0
        def submit(self,attempt):
            self.calls+=1
            raise TimeoutError('SECRET MUST NOT APPEAR')
    provider=Broken();service=AlertService(tmp_path,provider)
    assert service.automatic(incident()).result(timeout=5)['status']=='UNKNOWN'
    assert service.automatic(incident()).result(timeout=5)['status']=='WITHHELD'
    assert provider.calls==1
    assert 'SECRET' not in json.dumps(service.store.list())


def test_terminal_callback_cannot_regress(tmp_path):
    store=CallStore(tmp_path);identity,_=store.reserve(incident(),'mock','','manual','test')
    store.update(identity,'COMPLETED');store.update(identity,'RINGING')
    assert store.get(identity)['status']=='COMPLETED'


def test_validation_missing_or_dataset_only_stays_locked(tmp_path,monkeypatch):
    assert validation_reason(incident())
    import hashlib
    from src.alerts.service import engine_fingerprint
    p=tmp_path/'report.json';p.write_text(json.dumps({'engine_fingerprint':engine_fingerprint(),'scope':'dataset'}))
    monkeypatch.setenv('CALL_VALIDATION_REPORT',str(p));monkeypatch.setenv('CALL_VALIDATION_SHA256',hashlib.sha256(p.read_bytes()).hexdigest())
    assert 'Dataset evaluation' in validation_reason(incident())


def test_exotel_payload_calls_only_destination_and_configured_flow(monkeypatch):
    monkeypatch.setenv('EXOTEL_CALLER_ID','caller');monkeypatch.setenv('EXOTEL_FLOW_URL','https://my.exotel.com/account/exoml/start_voice/app')
    data=ExotelCallProvider.payload({'destination':'permitted','token':'opaque'})
    assert data['From']=='permitted' and 'To' not in data and data['CustomField']=='opaque'
    assert data['TimeLimit']==60
