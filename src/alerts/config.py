"""Fail-closed call configuration. Secrets never appear in status output."""
from dataclasses import dataclass
import os
import re
import sys


class CallsDisabled(RuntimeError):
    pass


def real_guard():
    # Re-read at the final provider boundary: cached config/UI cannot bypass this.
    if (os.getenv('REAL_CALLS_ENABLED','false').lower() != 'true'
        or os.getenv('CALL_MODE','test') != 'test'
        or os.getenv('CRASHZERO_V2_HOSTED') == '1'
        or os.getenv('CRASHZERO_HOSTED') == '1'
        or os.getenv('CI','').lower() in ('true','1')
        or 'pytest' in sys.modules or os.getenv('PYTEST_CURRENT_TEST')):
        raise CallsDisabled('Real calls disabled by backend policy.')
    if os.getenv('CRASHZERO_LOCAL_CALLS','false').lower() != 'true':
        raise CallsDisabled('Use the explicit local test-call launcher.')


REQUIRED = {
    'plivo': ('PLIVO_AUTH_ID','PLIVO_AUTH_TOKEN','PLIVO_FROM_NUMBER','CALLBACK_BASE_URL'),
    'exotel': ('EXOTEL_API_KEY','EXOTEL_API_TOKEN','EXOTEL_ACCOUNT_SID','EXOTEL_CALLER_ID','EXOTEL_FLOW_URL','CALLBACK_BASE_URL'),
    'mock': (),
}


@dataclass(frozen=True)
class CallConfig:
    provider: str
    destination: str
    auto: bool
    missing: tuple
    allowed: bool
    reason: str

    @classmethod
    def load(cls):
        provider = os.getenv('CALL_PROVIDER','mock').lower()
        destination = os.getenv('TEST_PHONE_NUMBER','')
        missing = [key for key in REQUIRED.get(provider,()) if not os.getenv(key)]
        if provider != 'mock' and not destination: missing.append('TEST_PHONE_NUMBER')
        reason = ''
        if provider not in REQUIRED: reason = 'Unknown CALL_PROVIDER.'
        elif os.getenv('CALL_MODE','test') != 'test': reason = 'Only CALL_MODE=test is supported.'
        elif provider != 'mock':
            try: real_guard()
            except CallsDisabled as exc: reason = str(exc)
            if not re.fullmatch(r'\+91[6-9]\d{9}', destination):
                reason = 'Configure one permitted Indian mobile test number in +91 format.'
            if os.getenv('TEST_PHONE_CONSENT','false').lower() != 'true':
                reason = 'TEST_PHONE_CONSENT must confirm permission for the configured test number.'
            if provider == 'plivo' and os.getenv('CALLBACK_BASE_URL','') and not os.environ['CALLBACK_BASE_URL'].startswith('https://'):
                reason = 'CALLBACK_BASE_URL must use public HTTPS.'
        if missing: reason = f'{provider.title()} configuration incomplete: '+', '.join(missing)
        return cls(provider,destination,os.getenv('AUTO_TEST_CALL_ENABLED','false').lower()=='true',tuple(missing),not reason,reason)

    @property
    def masked_destination(self):
        return ('••••'+self.destination[-4:]) if self.destination else 'Not configured'


def submission_guard(attempt, provider):
    real_guard()
    config=CallConfig.load()
    if not config.allowed or config.provider!=provider or attempt.get('destination')!=config.destination:
        raise CallsDisabled('Provider/destination/configuration is not authorized for this test call.')
