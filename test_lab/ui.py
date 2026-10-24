"""Simple automatic accident monitoring screen; evaluation data stays in SQLite."""
from pathlib import Path
import hashlib
import threading

import streamlit as st

from .analyzer import TestVideoAnalyzer
from .automatic import alert_state, run_automatic_verification
from .config import TestLabConfig
from .evidence_preview import render_evidence_preview
from .storage import TestHistory


def _save_upload(config, uploaded):
    content = uploaded.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    suffix = Path(uploaded.name).suffix.lower()
    path = config.uploads_dir / f'{digest[:20]}{suffix}'
    if not path.exists():
        path.write_bytes(content)
    return path


def render_alert(state, note=None):
    presentation = {
        'ALERT': ('#7f1d1d', 'RED — ALERT'),
        'NO ALERT': ('#14532d', 'GREEN — NO ALERT'),
        'REVIEW': ('#57534e', 'GREY — REVIEW'),
        'VERIFICATION UNAVAILABLE': ('#57534e', 'GREY — VERIFICATION UNAVAILABLE'),
        'ANALYZING': ('#475569', 'ANALYZING'),
        'NO SUSPICIOUS EVENT DETECTED': ('#475569', 'NO SUSPICIOUS EVENT DETECTED'),
        'READY': ('#475569', 'READY'),
    }
    background, label = presentation.get(state, presentation['VERIFICATION UNAVAILABLE'])
    st.markdown(
        f'<div role="status" style="background:{background};color:white;'
        'border-radius:18px;padding:42px 24px;text-align:center;'
        'font-size:clamp(2rem,5vw,4rem);font-weight:850;letter-spacing:.04em;'
        f'margin:18px 0 12px">{label}</div>', unsafe_allow_html=True)
    if note:
        st.caption('● System status: ' + note)


class UploadAnalysis:
    """Run analysis outside Streamlit's render thread so status updates can poll."""

    def __init__(self, config, videos):
        self.config = config
        self.videos = videos
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.ids = []
        self.done = False
        self.error = False
        self.thread = threading.Thread(target=self._run, daemon=True,
                                       name='CrashZero-TEST-upload')

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def snapshot(self):
        with self.lock:
            return list(self.ids), self.done, self.error

    def _run(self):
        history = TestHistory(self.config.db_path)
        try:
            analyzer = TestVideoAnalyzer(self.config)
            for path, name in self.videos:
                if self.stop_event.is_set():
                    break
                try:
                    row = analyzer.analyze(path, name)
                    if self.stop_event.is_set():
                        break
                    history.save(row)
                    with self.lock:
                        self.ids.append(row['test_id'])
                    for event in row['events']:
                        if self.stop_event.is_set():
                            break
                        verified = run_automatic_verification(
                            history, event['event_id'], kind='test',
                            budget_root=self.config.data_dir.parent)
                        # A confirmed accident already determines the upload's
                        # visible result; later candidates need no paid call.
                        if (verified and verified.get('status') == 'VERIFIED' and
                                verified.get('classification') == 'LIKELY_ACCIDENT'):
                            break
                except Exception:
                    with self.lock:
                        self.error = True
        finally:
            with self.lock:
                self.done = True


def _upload_changed():
    st.session_state['test_upload_generation'] = st.session_state.get('test_upload_generation', 0) + 1


def render_test_lab(data_dir=None):
    config = TestLabConfig.load(data_dir=data_dir)
    history = TestHistory(config.db_path)
    st.title('TEST · Accident Detection')
    # Reprocess an upload already selected in an open Streamlit session after
    # the candidate-timing fix; a stale green result must not survive reload.
    if st.session_state.get('test_pipeline_revision') != 'temporal-gap-1.5-v1':
        previous = st.session_state.get('test_upload_worker')
        if previous:
            previous.stop()
        st.session_state['test_upload_worker'] = None
        st.session_state['test_handled_generation'] = None
        st.session_state['test_pipeline_revision'] = 'temporal-gap-1.5-v1'
    uploads = st.file_uploader('Upload traffic video', type=['mp4', 'mov', 'avi', 'mkv'],
                               accept_multiple_files=True, key='test_lab_uploads',
                               on_change=_upload_changed)
    if uploads:
        st.video(str(_save_upload(config, uploads[0])))
    generation = st.session_state.get('test_upload_generation', 0)
    if uploads and generation != st.session_state.get('test_handled_generation'):
        previous = st.session_state.get('test_upload_worker')
        if previous:
            previous.stop()
        videos = [(_save_upload(config, upload), upload.name) for upload in uploads]
        worker = UploadAnalysis(config, videos)
        st.session_state['test_upload_worker'] = worker
        st.session_state['test_handled_generation'] = generation
        worker.start()
    elif not uploads and generation != st.session_state.get('test_handled_generation'):
        previous = st.session_state.get('test_upload_worker')
        if previous:
            previous.stop()
        st.session_state['test_upload_worker'] = None
        st.session_state['test_handled_generation'] = generation

    @st.fragment(run_every=1.0)
    def live_status():
        if st.session_state.get('cz_module') != 'TEST':
            return
        st.caption('Stage 2 — AI Accident Verification')
        worker = st.session_state.get('test_upload_worker')
        if not worker:
            render_alert('READY')
            render_evidence_preview([], history.submitted_evidence)
            return
        ids, done, failed = worker.snapshot()
        rows = [history.get(identity) for identity in ids]
        records = [event for row in rows if row for event in row['events']]
        if failed and not any(record and record.get('status') == 'VERIFIED' and
                              record.get('classification') == 'LIKELY_ACCIDENT'
                              for record in records):
            state, note = 'VERIFICATION UNAVAILABLE', 'Video analysis unavailable.'
        else:
            state, note = alert_state(records, analyzing=not done)
        render_alert(state, note)
        render_evidence_preview(records, history.submitted_evidence)

    live_status()
