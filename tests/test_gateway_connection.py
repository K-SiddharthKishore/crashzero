import sqlite3
import time

from module_2_accident_response.gateway_status import phone_monitoring
from module_2_accident_response.alerts import CallService
from module_2_accident_response.storage import AccidentRepository


def test_stale_call_expires_before_phone_can_collect_it(tmp_path, monkeypatch):
    monkeypatch.setenv('M2_GATEWAY_QUEUE_TTL_SECONDS','120')
    repo=AccidentRepository(tmp_path/'module2.sqlite3')
    repo.call({'id':'old-call','kind':'test','mode':'android_gateway','destination':'+919999999999',
               'message':'test','status':'QUEUED'})
    with sqlite3.connect(repo.path) as db:
        db.execute('UPDATE m2_call_attempts SET created_at=? WHERE id=?',(time.time()-300,'old-call'))
    assert repo.next_gateway_call() is None
    assert repo.call_by_id('old-call')['status']=='EXPIRED'
    assert [x['status'] for x in repo.status_history('old-call')]==['QUEUED','EXPIRED']
    assert phone_monitoring(repo)


def test_recent_call_is_collected_and_phone_poll_is_recorded(tmp_path):
    repo=AccidentRepository(tmp_path/'module2.sqlite3')
    assert not phone_monitoring(repo)
    repo.call({'id':'recent-call','kind':'test','mode':'android_gateway','destination':'+919999999999',
               'message':'test','status':'QUEUED'})
    assert repo.next_gateway_call()['id']=='recent-call'
    assert phone_monitoring(repo)


def test_withheld_alert_can_be_retried_without_call_count_or_cooldown(tmp_path,monkeypatch):
    repo=AccidentRepository(tmp_path/'module2.sqlite3')
    repo.call({'id':'withheld','incident_id':'incident-1','kind':'automatic','mode':'android_gateway',
               'destination':'+919999999999','message':'test','status':'WITHHELD'})
    before=repo.call_by_id('withheld')['created_at']
    monkeypatch.setenv('M2_CALL_MODE','real')
    monkeypatch.setenv('M2_REAL_CALLS_ENABLED','true')
    monkeypatch.setenv('M2_CALL_KILL_SWITCH','false')
    monkeypatch.setenv('M2_APPROVED_TEST_PHONE','+919999999999')
    monkeypatch.setenv('M2_TEST_PHONE_CONSENT','true')
    monkeypatch.setenv('M2_GATEWAY_TOKEN','x'*32)
    monkeypatch.setenv('M2_GATEWAY_MAX_CALLS_PER_HOUR','1')
    monkeypatch.setenv('M2_GATEWAY_COOLDOWN_SECONDS','3600')
    row=CallService(repo).retry('incident-1')
    assert row['id']=='withheld' and row['status']=='QUEUED'
    assert row['created_at']>=before
    assert [x['status'] for x in repo.status_history('withheld')]==['WITHHELD','QUEUED']
    try:
        CallService(repo).retry('incident-1')
    except ValueError as exc:
        assert 'Only withheld or expired alerts' in str(exc)
    else:
        assert False,'Queued alert must not be retried again'
    repo.call({'id':'second-withheld','incident_id':'incident-2','kind':'automatic','mode':'android_gateway',
               'destination':'+919999999999','message':'test','status':'WITHHELD'})
    assert CallService(repo).retry('incident-2')['status']=='QUEUED'
    assert [CallService(repo).submit(test=True)['status'] for _ in range(5)]==['QUEUED']*5
