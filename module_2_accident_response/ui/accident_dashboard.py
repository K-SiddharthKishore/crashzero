"""Accident monitoring presentation; detection and verification stay in AutomaticMonitor."""
from pathlib import Path
import hashlib

import streamlit as st

from test_lab.ui import render_alert
from test_lab.evidence_preview import render_evidence_preview
from src.presentation_settings import load_preferences
from ..config import Module2Config
from ..monitor import AutomaticMonitor, source_for
from ..storage import AccidentRepository


def _upload_changed():
    st.session_state['m2_upload_generation'] = st.session_state.get('m2_upload_generation', 0) + 1
    if st.session_state.get('m2_auto_upload') is None:
        st.session_state.pop('m2_saved_upload', None)


def _processing_stages(snapshot, records):
    if not snapshot or snapshot['state'] not in ('ANALYZING', 'READY'):
        return
    frames = snapshot['frames']
    incidents = snapshot['incidents']
    has_result = any(record and record.get('status') in ('VERIFIED', 'VERIFICATION_FAILED')
                     for record in records)
    finished = snapshot['status'] in ('COMPLETED', 'STOPPED', 'ERROR')
    steps = [
        ('Scanning Video', frames > 0, not frames and not finished),
        ('Detecting Suspicious Events', finished or incidents > 0, frames > 0 and not finished),
        ('Analysing Evidence', has_result, incidents > 0 and not has_result),
        ('Generating Result', finished and has_result, finished and incidents > 0 and not has_result),
    ]
    chips = ''.join(f'<span class="cz-stage {"done" if done else "active" if active else ""}">'
                    f'{number:02d} · {title}</span>'
                    for number, (title, done, active) in enumerate(steps, 1))
    st.markdown(f'<div class="cz-stage-row">{chips}</div>', unsafe_allow_html=True)


def _call_status(repository, identities):
    attempts = [repository.call_by_incident(identity) for identity in identities]
    attempts = [item for item in attempts if item]
    if not attempts:
        return 'Test Call Disabled', 'No phone request is queued from this monitor.'
    latest = attempts[-1]
    state = latest['status']
    labels = {
        'WITHHELD': 'Test Call Disabled',
        'QUEUED': 'Initiating Test Call',
        'RECEIVED': 'Initiating Test Call',
        'REQUIRES_CONFIRMATION': 'Awaiting Confirmation',
        'DIALING_REQUESTED': 'Call Initiated',
        'CALL_ACTIVE': 'Call Connected',
        'CALL_ENDED': 'Call Ended',
        'FAILED': 'Call Failed',
        'EXPIRED': 'Call Failed',
        'SIMULATED': 'Test Call Disabled',
    }
    detail = ('Tap the CrashZero notification on the phone to open the dialer.'
              if state == 'REQUIRES_CONFIRMATION' else
              'The phone gateway has received the request.' if state == 'RECEIVED' else
              'A dial request was submitted; answer is not confirmed.' if state == 'DIALING_REQUESTED' else
              'No real call was placed.' if state in ('WITHHELD', 'SIMULATED') else
              'Check the phone for call details.' if state in ('FAILED', 'EXPIRED') else
              'Call state reported by the Android phone.')
    return labels.get(state, 'Awaiting Confirmation'), detail


def render_dashboard(data_dir=None, hosted=False):
    cfg = Module2Config.load(data_dir=data_dir)
    repo = AccidentRepository(cfg.db_path)
    st.title('Accident Detector & Emergency Caller')
    st.markdown('<p class="cz-page-lead">Detect potential accidents and initiate rapid emergency response.</p>',
                unsafe_allow_html=True)
    st.markdown('<div class="cz-section-label">STAGE 1 — TRAFFIC EVENT DETECTION</div>', unsafe_allow_html=True)

    if st.session_state.get('m2_pipeline_revision') != 'short-cooldown-v1':
        previous = st.session_state.get('m2_monitor')
        if previous:
            previous.stop()
        st.session_state['m2_monitor'] = None
        st.session_state['m2_handled_generation'] = None
        st.session_state['m2_pipeline_revision'] = 'short-cooldown-v1'

    mode = st.segmented_control('Source', ['Upload Video', 'Live Camera'],
                                default='Upload Video', key='m2_source_mode',
                                label_visibility='collapsed')
    if mode != st.session_state.get('m2_previous_mode'):
        previous = st.session_state.get('m2_monitor')
        if previous:
            previous.stop()
        st.session_state['m2_monitor'] = None
        st.session_state['m2_previous_mode'] = mode
        if mode == 'Upload Video':
            st.session_state['m2_handled_generation'] = None
    monitor = st.session_state.get('m2_monitor')
    source_value = None
    camera_mode = None
    if mode == 'Upload Video':
        uploaded = st.file_uploader('Upload traffic video', type=['mp4', 'mov', 'avi', 'mkv'],
                                    key='m2_auto_upload', on_change=_upload_changed)
        if uploaded:
            data = uploaded.getvalue()
            digest = hashlib.sha256(data).hexdigest()
            folder = cfg.root / 'uploads'
            folder.mkdir(parents=True, exist_ok=True)
            source_value = folder / (digest[:20] + Path(uploaded.name).suffix.lower())
            if not source_value.exists():
                source_value.write_bytes(data)
            st.session_state['m2_saved_upload'] = {'path': str(source_value), 'digest': digest}
        elif st.session_state.get('m2_saved_upload'):
            saved = st.session_state['m2_saved_upload']
            source_value = Path(saved['path'])
            digest = saved['digest']
        generation = st.session_state.get('m2_upload_generation', 0)
        if generation != st.session_state.get('m2_handled_generation'):
            if monitor:
                monitor.stop()
            st.session_state['m2_monitor'] = None
            st.session_state['m2_handled_generation'] = generation
            if source_value:
                source = source_for('Upload', source_value, hosted=hosted)
                worker = AutomaticMonitor(cfg, source, source_key=digest[:20])
                st.session_state['m2_monitor'] = worker
                worker.start()
    else:
        camera_options = ['Network camera'] if hosted else ['Device webcam', 'Network camera']
        camera_mode = st.radio('Camera source', camera_options, horizontal=True,
                               key='m2_camera_kind')
        if camera_mode == 'Network camera':
            source_value = st.text_input('Camera stream URL', type='password',
                                         key='m2_stream_url',
                                         placeholder='rtsp://camera-address/stream')
        else:
            source_value = None
        monitor = st.session_state.get('m2_monitor')
        if not monitor or monitor.status in ('COMPLETED', 'STOPPED', 'ERROR'):
            if st.button('Start Monitoring', type='primary', use_container_width=True,
                         disabled=camera_mode == 'Network camera' and not source_value):
                try:
                    source = source_for('Camera' if camera_mode == 'Device webcam' else 'Network camera',
                                        source_value, hosted=hosted)
                    worker = AutomaticMonitor(cfg, source)
                    st.session_state['m2_monitor'] = worker
                    worker.start()
                    st.rerun()
                except ValueError:
                    st.error('This camera source is unavailable.')
        elif st.button('Stop Monitoring', use_container_width=True):
            monitor.stop()
            st.rerun()

    @st.fragment(run_every=1.0)
    def live_status():
        if st.session_state.get('cz_module') != 'Accident Response':
            return
        current = st.session_state.get('m2_monitor')
        snapshot = current.snapshot() if current else None
        if current:
            with current.lock:
                identities = list(current.incident_ids)
            records = [repo.verification(identity) for identity in identities]
        else:
            identities, records = [], []
        st.markdown('<div class="cz-section-label">STAGE 2 — AI ACCIDENT VERIFICATION</div>',
                    unsafe_allow_html=True)
        _processing_stages(snapshot, records)
        state = snapshot['state'] if snapshot else 'READY'
        render_alert(state, snapshot['note'] if snapshot else None)
        left, right = st.columns([1.8, 1], gap='large')
        with left:
            st.markdown('#### Traffic video')
            if mode == 'Upload Video' and source_value:
                st.video(str(source_value))
            elif snapshot and snapshot['preview'] is not None:
                st.image(snapshot['preview'], width='stretch')
            elif mode == 'Live Camera':
                st.info('Start monitoring to view the live camera feed.')
            else:
                st.info('Upload a video to begin analysis.')
        with right:
            st.markdown('#### Analysis Summary')
            st.metric('Suspicious events detected', snapshot['incidents'] if snapshot else 0)
            st.metric('Events verified', sum(row is not None and row.get('status') == 'VERIFIED'
                                             for row in records))
            st.caption('Processing: ' + (snapshot['status'].title() if snapshot else 'Ready'))
            st.caption('Verification result: ' + state.replace('_', ' ').title())
        if state == 'ALERT':
            title, detail = _call_status(repo, identities)
            st.markdown('<div class="cz-section-label">EMERGENCY RESPONSE</div>',
                        unsafe_allow_html=True)
            st.markdown(f'<div class="cz-panel"><h3>{title}</h3><p>{detail}</p></div>',
                        unsafe_allow_html=True)
        show_evidence = load_preferences(cfg.db_path.parent.parent)['show_evidence']
        render_evidence_preview(records, repo.submitted_evidence, enabled=show_evidence)

    live_status()
