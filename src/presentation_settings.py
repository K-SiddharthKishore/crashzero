"""Persistent presentation preferences and a bounded local test-call settings UI."""
import json
import os
import re
from pathlib import Path

import streamlit as st

from module_2_accident_response.alerts import EMERGENCY
from module_2_accident_response.config import Module2Config
from module_2_accident_response.gateway_status import phone_monitoring
from module_2_accident_response.storage import AccidentRepository

DEFAULTS = {'show_evidence': True}


def load_preferences(storage_root):
    path = Path(storage_root) / 'ui_preferences.json'
    try:
        stored = json.loads(path.read_text())
        return {**DEFAULTS, **{key: stored[key] for key in DEFAULTS if isinstance(stored.get(key), bool)}}
    except (OSError, ValueError, TypeError):
        return DEFAULTS.copy()


def _save_preferences(storage_root, values):
    path = Path(storage_root) / 'ui_preferences.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(values, indent=2))
    temporary.replace(path)


def _save_local_call_config(updates):
    """Change only these non-secret call fields; retain all existing .env entries."""
    from config.settings import ROOT
    path = ROOT / '.env'
    lines = path.read_text().splitlines() if path.exists() else []
    seen = set()
    output = []
    for line in lines:
        key = line.split('=', 1)[0]
        if key in updates:
            if key not in seen:
                output.append(f'{key}={updates[key]}')
                seen.add(key)
        else:
            output.append(line)
    output.extend(f'{key}={value}' for key, value in updates.items() if key not in seen)
    path.write_text('\n'.join(output) + '\n')
    for key, value in updates.items():
        os.environ[key] = value


def render_settings(storage_root, hosted=False):
    st.title('Settings')
    st.markdown('<p class="cz-page-lead">Configure presentation and review the test response connection.</p>',
                unsafe_allow_html=True)
    preferences = load_preferences(storage_root)
    st.markdown('<div class="cz-section-label">SYSTEM PREFERENCES</div>', unsafe_allow_html=True)
    with st.form('presentation_preferences'):
        show_evidence = st.toggle('Show Evidence Frames', value=preferences['show_evidence'],
                                  help='Shows the actual submitted JPEGs in a collapsed section. No extra verification request is made.')
        st.caption('Analysis results are saved automatically. Live camera sources remain available when supported by this host.')
        st.caption('Sound alerts are unavailable in this version.')
        save_presentation = st.form_submit_button('Save Settings', type='primary')
    if save_presentation:
        _save_preferences(storage_root, {'show_evidence': show_evidence})
        st.success('Display settings saved.')

    st.markdown('<div class="cz-section-label">EMERGENCY CALL CONFIGURATION</div>', unsafe_allow_html=True)
    st.caption('Only an approved non-emergency test number may receive a call request. TEST alerts require confirmation in the Oppo app before dialing.')
    if hosted:
        st.info('Phone gateway settings are available only on the computer connected to the Android phone.')
        return
    repository = AccidentRepository(Module2Config.load().db_path)
    st.caption('Phone gateway: connected' if phone_monitoring(repository) else 'Phone gateway: not connected')
    current_number = os.getenv('M2_APPROVED_TEST_PHONE', '')
    with st.form('call_preferences'):
        allow_test_alerts = st.toggle('Enable Automatic Test Calling',
                                      value=os.getenv('M2_TEST_ALERT_CALLS_ENABLED', 'false').lower() == 'true',
                                      help='Automatically sends one request for a verified TEST video. The Oppo app still requires your tap to dial.')
        number = st.text_input('Authorized Test Phone Number', value=current_number, type='password')
        mode = st.selectbox('Test Calling Mode', ['mock', 'real'],
                            index=1 if os.getenv('M2_CALL_MODE', 'mock').lower() == 'real' else 0)
        st.caption('Call cooldown: duplicate requests for the same uploaded video are blocked. A separate time-based cooldown is not configurable in this build.')
        save_call = st.form_submit_button('Save Call Settings')
    if save_call:
        digits = re.sub(r'\D', '', number)
        if allow_test_alerts and (not 8 <= len(digits) <= 15 or digits in EMERGENCY):
            st.error('Enter an approved non-emergency test number with 8–15 digits.')
        elif number and not re.fullmatch(r'\+?[0-9]{8,15}', number):
            st.error('Use digits and an optional leading + for the test number.')
        else:
            _save_local_call_config({
                'M2_TEST_ALERT_CALLS_ENABLED': 'true' if allow_test_alerts else 'false',
                'M2_APPROVED_TEST_PHONE': number,
                'M2_CALL_MODE': mode,
            })
            st.success('Call settings saved. Update the approved number in the Oppo app too if you changed it.')
    if os.getenv('M2_REAL_CALLS_ENABLED', 'false').lower() != 'true' or os.getenv('M2_CALL_KILL_SWITCH', 'true').lower() == 'true':
        st.info('Real test calling is disabled by the server configuration.')
