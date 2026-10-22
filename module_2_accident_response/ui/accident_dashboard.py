from pathlib import Path
import hashlib
import streamlit as st
from ..alerts import CallService
from ..config import Module2Config
from ..pipeline import Module2Analyzer
from ..storage import AccidentRepository

def render_dashboard(data_dir=None):
    cfg=Module2Config.load(data_dir=data_dir); repo=AccidentRepository(cfg.db_path); calls=CallService(repo)
    st.title('Accident Response')
    st.caption('Upload a recorded video · review possible accidents · inspect evidence and alert history')
    st.markdown('<div class="cz-section-label">STEP 1 / RECORDED VIDEO</div>',unsafe_allow_html=True)
    st.subheader('Analyze a recording')
    st.caption('Results are experimental candidates. Review the evidence before treating any event as an accident.')
    with st.expander('Advanced settings · camera and calling'):
        a,b,c=st.columns(3); camera_id=a.text_input('Camera ID',value='M2-UPLOAD');camera_name=b.text_input('Camera name',value='Recorded CCTV');location=c.text_input('Camera location',value='Location not configured')
        repo.save_camera(camera_id,camera_name,location)
        setting=calls.settings();st.caption(f"Call mode: {setting['mode'].upper()} · delivery: {'Android SIM gateway' if setting['mode']=='real' else 'simulation'} · recipient {'configured' if setting['recipient'] else 'not configured'} · real calling {'enabled' if setting['enabled'] and not setting['kill'] else 'disabled'}")
        if st.button('Test Call',help='Uses only the configured approved, consenting non-emergency test number.'):
            row=calls.submit(test=True);st.write(f"{row['status']}: {row.get('detail') or 'request stored; Android gateway will poll for it'}")
    uploaded=st.file_uploader('Upload recorded CCTV video',type=['mp4','mov','avi','mkv'],key='m2_upload')
    if uploaded:
        folder=cfg.root/'uploads';folder.mkdir(exist_ok=True);suffix=Path(uploaded.name).suffix.lower();dest=folder/(hashlib.sha256(uploaded.getvalue()).hexdigest()[:20]+suffix)
        if st.session_state.get('m2_result_source') not in (None,str(dest)):
            for key in ('m2_latest_result','m2_latest_alert','m2_pending_review_call'):
                st.session_state.pop(key,None)
        if not dest.exists():dest.write_bytes(uploaded.getvalue())
        st.video(str(dest))
        if st.button('Start Analysis',type='primary'):
            bar=st.progress(0.0); status=st.empty()
            try:
                incident,report=Module2Analyzer(cfg).analyze_file(dest,camera_id,location,bar.progress)
                st.session_state['m2_latest_result']={'incident':incident,'report':report}
                st.session_state['m2_result_source']=str(dest)
                st.session_state.pop('m2_latest_alert',None)
                st.session_state.pop('m2_pending_review_call',None)
                if incident:
                    repo.save_incident(incident); status.warning('Possible accident found. Review the evidence below.')
                    if incident.get('temporal_model'):
                        st.session_state['m2_pending_review_call'] = incident
                    else:
                        row=calls.submit(incident)
                        st.session_state['m2_latest_alert']=f"Automatic alert: {row['status']} — {row.get('detail') or row['mode'].upper()}"
                else:status.success(report['reason'])
            except Exception as exc:
                st.session_state.pop('m2_latest_result',None)
                status.error('Analysis could not run: '+str(exc))
    result=st.session_state.get('m2_latest_result')
    if result:
        st.markdown('<div class="cz-section-label">STEP 2 / REVIEW RESULT</div>',unsafe_allow_html=True)
        incident=result['incident']
        if incident:
            st.warning('POSSIBLE ACCIDENT · experimental candidate')
            st.write(incident['explanation'])
            if Path(incident['screenshot_path']).exists():st.image(incident['screenshot_path'],width='stretch')
            if Path(incident['clip_path']).exists():st.video(incident['clip_path'])
            if incident.get('temporal_model'):
                st.info('No alert was sent. Review this experimental result before approving an alert.')
            elif st.session_state.get('m2_latest_alert'):
                st.caption(st.session_state['m2_latest_alert'])
        else:
            st.success(result['report']['reason'])
        st.caption(result['report']['model'])
    pending=st.session_state.get('m2_pending_review_call')
    if pending:
        st.caption('Temporal-model candidate is awaiting a human decision; it is not sent to the call gateway automatically.')
        if st.button('I reviewed this clip — send alert through existing gateway',key='m2_approve_temporal_call'):
            row=calls.submit(pending)
            st.session_state.pop('m2_pending_review_call',None)
            st.write(f"{row['status']}: {row.get('detail') or row['mode'].upper()}")
    st.markdown('<div class="cz-section-label">'+('STEP 3' if result else 'PAST ANALYSES')+' / SAVED HISTORY</div>',unsafe_allow_html=True)
    st.subheader('Incident evidence')
    incidents=repo.incidents()
    if not incidents: st.caption('No Module 2 incidents saved.')
    for i in incidents:
        with st.expander(f"{i['incident_id']} · {i['state']} · {i['score']:.2f}"):
            st.write(i['explanation']);st.caption(f"Offset: {i['event_offset']:.1f}s · {i['location']}")
            if i['clip_path'] and Path(i['clip_path']).exists():st.video(i['clip_path'])
    with st.expander('Alert history'):
        history=repo.calls()
        if history:st.dataframe([{k:r.get(k) for k in ('created_at','kind','mode','status','incident_id','destination','detail')} for r in history],hide_index=True,width='stretch')
        else:st.caption('No call attempts saved. Mock mode is the default.')
