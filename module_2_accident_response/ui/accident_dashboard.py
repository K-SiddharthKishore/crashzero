"""Minimal automatic accident monitoring interface for Module 2."""
from pathlib import Path
import hashlib

import streamlit as st

from test_lab.ui import render_alert
from test_lab.evidence_preview import render_evidence_preview
from ..config import Module2Config
from ..monitor import AutomaticMonitor, source_for
from ..storage import AccidentRepository


def _upload_changed():
    st.session_state['m2_upload_generation'] = st.session_state.get('m2_upload_generation', 0) + 1


def render_dashboard(data_dir=None, hosted=False):
    cfg = Module2Config.load(data_dir=data_dir)
    repo = AccidentRepository(cfg.db_path)
    st.title('Accident Response')

    if st.session_state.get('m2_pipeline_revision') != 'short-cooldown-v1':
        previous = st.session_state.get('m2_monitor')
        if previous:
            previous.stop()
        st.session_state['m2_monitor'] = None
        st.session_state['m2_handled_generation'] = None
        st.session_state['m2_pipeline_revision'] = 'short-cooldown-v1'

    mode = st.radio('Video source', ['Upload', 'Camera', 'Network camera'], horizontal=True,
                    key='m2_source_mode')
    if mode != st.session_state.get('m2_previous_mode'):
        previous = st.session_state.get('m2_monitor')
        if previous:
            previous.stop()
        st.session_state['m2_monitor'] = None
        st.session_state['m2_previous_mode'] = mode
        if mode == 'Upload':
            st.session_state['m2_handled_generation'] = None
    monitor = st.session_state.get('m2_monitor')
    source_value = None
    if mode == 'Upload':
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
            st.video(str(source_value))
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
    elif mode == 'Network camera':
        source_value = st.text_input('Camera stream URL', type='password', key='m2_stream_url')

    @st.fragment(run_every=1.0)
    def live_status():
        current = st.session_state.get('m2_monitor')
        snapshot = current.snapshot() if current else None
        if snapshot and current.source.live and snapshot['preview'] is not None:
            st.image(snapshot['preview'], width='stretch')
        st.caption('Stage 2 — AI Accident Verification')
        render_alert(snapshot['state'] if snapshot else 'READY',
                     snapshot['note'] if snapshot else None)
        if current:
            with current.lock:
                identities = list(current.incident_ids)
            records = [repo.verification(identity) for identity in identities]
        else:
            records = []
        render_evidence_preview(records, repo.submitted_evidence)

    live_status()
    if mode != 'Upload':
        monitor = st.session_state.get('m2_monitor')
        if not monitor or monitor.status in ('COMPLETED', 'STOPPED', 'ERROR'):
            if st.button('Start monitoring', type='primary', use_container_width=True,
                         disabled=mode == 'Network camera' and not source_value):
                try:
                    source = source_for(mode, source_value, hosted=hosted)
                    worker = AutomaticMonitor(cfg, source)
                    st.session_state['m2_monitor'] = worker
                    worker.start()
                    st.rerun()
                except ValueError:
                    st.error('This camera source is unavailable.')
        elif st.button('Stop monitoring', use_container_width=True):
            monitor.stop()
            st.rerun()
