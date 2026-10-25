"""Safe mock/Plivo adapter.  Real calls are opt-in and allowlist constrained."""
import os
import re
import uuid
from .storage import AccidentRepository

EMERGENCY={'112','100','101','102','108','911'}

def clean_location(value):
    return re.sub(r'[^A-Za-z0-9 ,.-]',' ',value or '')[:120].strip() or 'location not configured'

class CallService:
    def __init__(self, repository): self.repository=repository
    def settings(self):
        return {'mode':os.getenv('M2_CALL_MODE','mock').lower(),'enabled':os.getenv('M2_REAL_CALLS_ENABLED','false').lower()=='true',
                'kill':os.getenv('M2_CALL_KILL_SWITCH','true').lower()=='true','recipient':os.getenv('M2_APPROVED_TEST_PHONE','').strip(),
                'consent':os.getenv('M2_TEST_PHONE_CONSENT','false').lower()=='true',
                'temporal_auto':os.getenv('M2_TEMPORAL_AUTO_CALLS_ENABLED','false').lower()=='true'}
    def _allowed(self, s):
        digits=re.sub(r'\D','',s['recipient'])
        if not digits or digits in EMERGENCY or not s['consent']: return False,'Approved, consenting non-emergency test recipient required.'
        if s['mode']=='real' and (not s['enabled'] or s['kill']): return False,'Real demo calling is disabled or kill switch is active.'
        if s['mode'] not in ('mock','real'): return False,'Call mode must be mock or real.'
        if s['mode']=='real' and os.getenv('M2_CALL_PROVIDER','android_gateway').lower()!='android_gateway':
            return False,'Real Module 2 calls require the Android gateway.'
        if s['mode']=='real':
            if len(os.getenv('M2_GATEWAY_TOKEN',''))<32:return False,'A private Android gateway token of at least 32 characters is required.'
        return True,None
    def message(self,incident,test=False):
        location=clean_location(incident.get('location'))
        if test:return 'Hello. This is a CrashZero test call. The accident response phone connection is being tested.'
        prefix='Hello. This is a CrashZero demonstration alert.' if incident.get('source_kind')=='uploaded video' else 'Hello. This is an automated alert from CrashZero.'
        recording='recorded CCTV footage' if incident.get('source_kind')=='uploaded video' else 'live CCTV'
        return f'{prefix} A possible road accident was detected in {recording} from {location}. Incident ID {incident["incident_id"]}. This alert is automated and unverified. Please review the evidence.'
    def submit(self,incident=None,test=False):
        s=self.settings(); ok,reason=self._allowed(s)
        message=self.message(incident or {},test)
        if not test:
            previous=self.repository.call_by_incident(incident['incident_id'])
            if previous:return previous
        delivery='mock' if s['mode']=='mock' else 'android_gateway'
        row={'id':'m2-call-'+uuid.uuid4().hex[:12],'incident_id':None if test else incident['incident_id'],'kind':'test' if test else 'automatic','mode':delivery,'destination':s['recipient'],'message':message,'status':'WITHHELD' if not ok else 'SIMULATED' if s['mode']=='mock' else 'QUEUED','detail':reason}
        self.repository.call(row)
        return row
    def submit_verified_test_alert(self, source_sha256):
        """Queue one phone-confirmed demo alert per uploaded TEST video."""
        if os.getenv('M2_TEST_ALERT_CALLS_ENABLED','false').lower() != 'true':
            return None
        if not re.fullmatch(r'[0-9a-f]{64}', source_sha256):
            raise ValueError('A valid uploaded-video digest is required.')
        incident_id = 'CZ-TEST-ALERT-' + source_sha256[:32]
        previous = self.repository.call_by_incident(incident_id, kind='verified_test')
        if previous:
            return previous
        settings = self.settings()
        allowed, reason = self._allowed(settings)
        delivery = 'mock' if settings['mode'] == 'mock' else 'android_gateway'
        row = {
            'id': 'm2-call-' + uuid.uuid4().hex[:12],
            'incident_id': incident_id,
            'kind': 'verified_test',
            'mode': delivery,
            'destination': settings['recipient'],
            'message': ('CrashZero TEST alert: Stage 2 classified a likely accident '
                        'in uploaded footage. Review the evidence before taking action.'),
            'status': 'WITHHELD' if not allowed else 'SIMULATED' if delivery == 'mock' else 'QUEUED',
            'detail': reason,
        }
        return self.repository.call_once(row)
    def retry(self,incident_id):
        previous=self.repository.call_by_incident(incident_id)
        if not previous or previous['status'] not in ('WITHHELD','EXPIRED'):
            raise ValueError('Only withheld or expired alerts can be retried.')
        allowed,reason=self._allowed(self.settings())
        if not allowed:
            raise ValueError(reason)
        row=self.repository.requeue_call(previous['id'])
        if not row:
            raise ValueError('This alert is no longer available for retry.')
        return row
