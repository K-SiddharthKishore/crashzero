"""Stricter eligibility and bounded, audited test notifications."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import os
import time
import uuid
from config.settings import ROOT
from config.v2 import SAFETY
from .config import CallConfig, real_guard, CallsDisabled
from .providers import provider_for
from .store import CallStore

EXECUTOR=ThreadPoolExecutor(max_workers=2,thread_name_prefix='CrashZero-test-call')
MANUAL_MESSAGE='CrashZero test notification. The calling system is configured correctly. This is only a test.'


def engine_fingerprint():
    digest=hashlib.sha256(json.dumps(asdict(SAFETY),sort_keys=True).encode())
    for relative in ('src/safety/verifier.py','src/trajectory.py','src/conflicts.py',
                     'src/video/camera_motion.py','src/calibration.py','src/detector.py','config/settings.py','config/bytetrack-v2.yaml'):
        digest.update((ROOT/relative).read_bytes())
    model=ROOT/'models/yolo11n.pt'
    if model.exists():
        with model.open('rb') as source: digest.update(hashlib.file_digest(source,'sha256').digest())
    return digest.hexdigest()


def configuration_key(config):
    fields=[config.provider,config.destination,os.getenv('PLIVO_FROM_NUMBER',''),os.getenv('PLIVO_AUTH_ID',''),
            os.getenv('EXOTEL_CALLER_ID',''),os.getenv('EXOTEL_ACCOUNT_SID',''),os.getenv('EXOTEL_FLOW_URL','')]
    return hashlib.sha256(json.dumps(fields).encode()).hexdigest()


def validation_reason(incident):
    path=os.getenv('CALL_VALIDATION_REPORT','')
    approved=os.getenv('CALL_VALIDATION_SHA256','')
    if not path or not approved: return 'No explicitly approved real-footage validation report.'
    try:
        content=Path(path).read_bytes()
        if hashlib.sha256(content).hexdigest()!=approved: return 'Validation report changed since approval.'
        report=json.loads(content)
        if report.get('engine_fingerprint')!=engine_fingerprint(): return 'Validation is stale for this engine/configuration.'
        if report.get('scope')!='deployment-camera': return 'Dataset evaluation does not validate this deployment camera.'
        if not report.get('reviewed_by') or not report.get('real_auto_test_approved'): return 'Validation has not been explicitly approved.'
        if report.get('positive_events',0)<=0 or report.get('negative_hours',0)<=0: return 'Validation lacks labelled positives or negative exposure.'
        if report.get('call_false_positives')!=0: return 'Call-gate false positives are unresolved.'
        target=incident.get('source_id') if incident.get('source_kind')=='live camera' else incident.get('media_digest')
        if target not in report.get('approved_sources',[]): return 'This source was not reviewed for automatic test calling.'
        if report.get('camera_config_hashes',{}).get(target)!=incident.get('camera_config_hash'): return 'Camera calibration/corridors changed since validation.'
    except (OSError,ValueError,TypeError): return 'Validation report unavailable or invalid.'
    return None


class CallEligibilityGate:
    def evaluate(self, incident, config, store):
        reasons=[]
        if incident.get('phase')!='LIKELY_ACCIDENT': reasons.append('Event is not temporally verified as likely accident.')
        groups=incident.get('evidence_groups',{})
        required=['IMPACT','AFTERMATH'] if incident.get('single') else ['INTERACTION','IMPACT','AFTERMATH']
        if not all(groups.get(key) for key in required): reasons.append('Independent evidence groups are incomplete.')
        if not incident.get('temporal_coverage') or incident.get('missing'): reasons.append('Temporal coverage is insufficient.')
        if not incident.get('camera_motion_safe'): reasons.append('Camera motion is unresolved.')
        if incident.get('minimum_tracking_confidence',0)<.6: reasons.append('Tracking confidence is insufficient for calling.')
        if incident.get('evidence_status')!='EVIDENCE SAVED' or incident.get('pre_event_truncated') or incident.get('post_event_truncated'):
            reasons.append('Complete before/event/after evidence is unavailable.')
        if not config.auto: reasons.append('AUTO_TEST_CALL_ENABLED is off.')
        if not config.allowed: reasons.append(config.reason)
        if config.provider!='mock':
            if 'SYNTHETIC' in incident.get('source_kind','').upper(): reasons.append('Synthetic fixtures cannot trigger real automatic calls.')
            if not store.acknowledged(configuration_key(config)): reasons.append('Complete and acknowledge a manual provider test first.')
            reason=validation_reason(incident)
            if reason: reasons.append(reason)
        return {'passed':not reasons,'reasons':reasons,'provider':config.provider,'evaluated_at':time.time()}


class AlertService:
    def __init__(self, root=None, provider=None):
        self.store=CallStore(root or ROOT/'outputs/calls')
        self.injected_provider=provider

    def manual(self):
        return EXECUTOR.submit(self._submit, {'incident_id':'manual-'+uuid.uuid4().hex}, 'manual', MANUAL_MESSAGE)

    def automatic(self, incident):
        return EXECUTOR.submit(self._automatic,dict(incident))

    def _automatic(self, incident):
        config=CallConfig.load()
        result=CallEligibilityGate().evaluate(incident,config,self.store)
        self.store.eligibility(incident['incident_id'],result)
        if not result['passed']: return {'status':'WITHHELD',**result}
        event_time=incident.get('observed_at') or f"recording offset {incident.get('timestamp',0):.1f} seconds"
        message=(f"CrashZero test alert. A likely road accident has been detected by Camera {incident.get('camera_id','unknown')} "
                 f"at {incident.get('registered_location','location not configured')} at {event_time}. "
                 'The event passed automated accident verification. This is a test notification.')
        return self._submit(incident,'automatic',message)

    def _submit(self, incident, kind, message):
        config=CallConfig.load()
        if not config.allowed: return {'status':'WITHHELD','reason':config.reason}
        if kind=='automatic':
            result=CallEligibilityGate().evaluate(incident,config,self.store)
            if not result['passed']: return {'status':'WITHHELD',**result}
        # Dependency injection can only replace mock providers, never bypass real policy.
        real=config.provider!='mock'
        if real:
            try: real_guard()
            except CallsDisabled as exc: return {'status':'WITHHELD','reason':str(exc)}
        identity,reason=self.store.reserve(incident,config.provider,config.destination,kind,message,real=real)
        if not identity: return {'status':'WITHHELD','reason':reason}
        provider=self.injected_provider if self.injected_provider and not real else provider_for(config.provider)
        self.store.update(identity,'SUBMITTING')
        try:
            if real: real_guard()
            provider_id,status=provider.submit(self.store.get(identity))
            self.store.update(identity,status,provider_id)
        except CallsDisabled:
            self.store.update(identity,'FAILED',detail='Backend kill switch blocked submission.')
        except Exception as exc:
            # Never repeat an ambiguous submission. Exception text can contain credentials.
            self.store.update(identity,'UNKNOWN',detail='Provider outcome unknown: '+type(exc).__name__+'. No automatic retry.')
        if real and self.store.get(identity)['status'] in ('INITIATED','RINGING','ANSWERED'):
            self._poll(identity,provider)
        row=self.store.get(identity)
        return {'id':identity,'status':row['status']}

    def _poll(self, identity, provider):
        # Polling only reads status; it never resubmits or retries a call.
        for _ in range(40):
            time.sleep(2)
            row=self.store.get(identity)
            if row['status'] in ('COMPLETED','FAILED'): break
            try: status=provider.status(row['provider_call_id'])
            except Exception: continue
            if status!='UNKNOWN': self.store.update(identity,status)
            if status in ('COMPLETED','FAILED'): break

    def reconcile(self, identity):
        row=self.store.get(identity)
        if not row or not row['provider_call_id']: return 'UNKNOWN'
        try:
            status=provider_for(row['provider']).status(row['provider_call_id'])
            if status!='UNKNOWN': self.store.update(identity,status)
            return status
        except Exception: return 'UNKNOWN'
