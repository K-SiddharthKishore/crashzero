from src.presentation_settings import load_preferences, _save_preferences
from module_2_accident_response.ui.accident_dashboard import _call_status


def test_evidence_preference_persists_without_other_settings(tmp_path):
    assert load_preferences(tmp_path)['show_evidence'] is True
    _save_preferences(tmp_path, {'show_evidence': False})
    assert load_preferences(tmp_path)['show_evidence'] is False


def test_call_status_never_claims_connection_from_dial_request():
    class Repository:
        def __init__(self, status):
            self.status = status

        def call_by_incident(self, identity):
            return {'status': self.status}

    assert _call_status(Repository('DIALING_REQUESTED'), ['incident'])[0] == 'Call Initiated'
    assert _call_status(Repository('REQUIRES_CONFIRMATION'), ['incident'])[0] == 'Awaiting Confirmation'
    assert _call_status(Repository('CALL_ACTIVE'), ['incident'])[0] == 'Call Connected'
