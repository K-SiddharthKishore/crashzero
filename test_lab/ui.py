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


def _send_verified_test_alert(source_sha256):
    """Send only a phone-confirmed test alert; never dial from verification."""
    from module_2_accident_response.alerts import CallService
    from module_2_accident_response.config import Module2Config
    from module_2_accident_response.storage import AccidentRepository

    repo = AccidentRepository(Module2Config.load().db_path)
    return CallService(repo).submit_verified_test_alert(source_sha256)


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
        'ALERT': ('alert', 'RED — ACCIDENT DETECTED'),
        'NO ALERT': ('safe', 'GREEN — NO ACCIDENT EVIDENCE'),
        'REVIEW': ('review', 'GREY — NEEDS REVIEW'),
        'VERIFICATION UNAVAILABLE': ('review', 'VERIFICATION UNAVAILABLE'),
        'ANALYZING': ('progress', 'ANALYSING VIDEO'),
        'NO SUSPICIOUS EVENT DETECTED': ('neutral', 'NO SUSPICIOUS EVENT DETECTED'),
        'READY': ('neutral', 'READY TO ANALYSE'),
    }
    tone, label = presentation.get(state, presentation['VERIFICATION UNAVAILABLE'])
    st.markdown(
        f'<div role="status" class="cz-result {tone}"><div class="eyebrow">VERIFICATION RESULT</div>'
        f'<div class="title">{label}</div></div>', unsafe_allow_html=True)
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
                            _send_verified_test_alert(row['source_sha256'])
                            break
                except Exception:
                    with self.lock:
                        self.error = True
        finally:
            with self.lock:
                self.done = True


def _upload_changed():
    st.session_state['test_upload_generation'] = st.session_state.get('test_upload_generation', 0) + 1
    if not st.session_state.get('test_lab_uploads'):
        st.session_state.pop('test_saved_uploads', None)


def render_test_lab(data_dir=None, *, embedded=False):
    config = TestLabConfig.load(data_dir=data_dir)
    history = TestHistory(config.db_path)
    if embedded:
        st.title('Accident Detection')
        st.caption('Upload a traffic video. Analysis starts automatically.')
    else:
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
    @st.fragment(run_every=1.0)
    def upload_flow():
        from src.ui_flow import render_flow
        active = st.session_state.get('test_upload_worker')
        if active:
            _, done, failed = active.snapshot()
            render_flow(['Upload', 'AI Analysis', 'Result'],
                        current=2 if done else 1,
                        completed=(0, 1) if done and not failed else (0,))
        else:
            render_flow(['Upload', 'AI Analysis', 'Result'])
    upload_flow()

    uploads = st.file_uploader('Upload traffic video', type=['mp4', 'mov', 'avi', 'mkv'],
                               accept_multiple_files=True, key='test_lab_uploads',
                               on_change=_upload_changed)
    if uploads:
        saved = [(_save_upload(config, upload), upload.name) for upload in uploads]
        st.session_state['test_saved_uploads'] = [(str(path), name) for path, name in saved]
    else:
        saved = [(Path(path), name) for path, name in st.session_state.get('test_saved_uploads', [])]
    generation = st.session_state.get('test_upload_generation', 0)
    if saved and generation != st.session_state.get('test_handled_generation'):
        previous = st.session_state.get('test_upload_worker')
        if previous:
            previous.stop()
        videos = saved
        worker = UploadAnalysis(config, videos)
        st.session_state['test_upload_worker'] = worker
        st.session_state['test_handled_generation'] = generation
        worker.start()
    elif not saved and generation != st.session_state.get('test_handled_generation'):
        previous = st.session_state.get('test_upload_worker')
        if previous:
            previous.stop()
        st.session_state['test_upload_worker'] = None
        st.session_state['test_handled_generation'] = generation

    @st.fragment(run_every=1.0)
    def live_status():
        if st.session_state.get('cz_module') not in ('TEST','Accident Response'):
            return
        from src.presentation_settings import load_preferences
        display_evidence=load_preferences(config.data_dir.parent)['show_evidence']
        worker = st.session_state.get('test_upload_worker')
        if not worker:
            render_alert('READY')
            render_evidence_preview([], history.submitted_evidence,enabled=display_evidence)
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
        if saved:
            video_column, result_column = st.columns([1.65, 1], gap='medium')
            with video_column:
                st.video(str(saved[0][0]))
            with result_column:
                render_alert(state, note)
        else:
            render_alert(state, note)
        if state == 'ALERT':
            from module_2_accident_response.config import Module2Config
            from module_2_accident_response.storage import AccidentRepository
            call_repo=AccidentRepository(Module2Config.load(
                data_dir=config.data_dir.parent/'module2_accident_response').db_path)
            confirmed=next((row for row in rows if row and any(
                event.get('status') == 'VERIFIED' and
                event.get('classification') == 'LIKELY_ACCIDENT'
                for event in row['events'])),None)
            call=(call_repo.call_by_incident('CZ-TEST-ALERT-'+confirmed['source_sha256'][:32],
                                            kind='verified_test') if confirmed else None)
            labels={'QUEUED':'Initiating Test Call','RECEIVED':'Initiating Test Call',
                    'REQUIRES_CONFIRMATION':'Awaiting Confirmation',
                    'DIALING_REQUESTED':'Call Initiated','CALL_ACTIVE':'Call Connected',
                    'CALL_ENDED':'Call Ended','FAILED':'Call Failed','EXPIRED':'Call Failed',
                    'WITHHELD':'Test Call Disabled','SIMULATED':'Test Call Disabled'}
            title=labels.get(call['status'],'Test Call Disabled') if call else 'Test Call Disabled'
            detail=('Tap the CrashZero phone notification to confirm dialing.'
                    if call and call['status']=='REQUIRES_CONFIRMATION' else
                    'The phone has not confirmed an answered call.' if call else
                    'No phone request was sent for this result.')
            st.markdown('<div class="cz-section-label">EMERGENCY RESPONSE</div>',
                        unsafe_allow_html=True)
            st.markdown(f'<div class="cz-panel"><h3>{title}</h3><p>{detail}</p></div>',
                        unsafe_allow_html=True)
        render_evidence_preview(records, history.submitted_evidence,enabled=display_evidence)

    live_status()
