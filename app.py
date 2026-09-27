"""CrashZero V2 — three focused screens; V1 remains available in app_v1.py."""
from pathlib import Path
import hashlib
import json
import os
import uuid
import streamlit as st
from config.settings import ROOT, category
from src.incidents.manager import IncidentStore
from src.zones import conflict_zones

HOSTED_V2 = os.environ.get('CRASHZERO_V2_HOSTED') == '1'

st.set_page_config(page_title='CrashZero · Predict Risk Before Impact',page_icon='◉',layout='wide')
st.markdown('''<style>
.stApp {background:#101315;color:#eee;}
.block-container {max-width:1480px;padding-top:2rem;}
h1 {font-size:1.7rem !important;letter-spacing:.025em;}
[data-testid="stMetricValue"] {font-size:1.7rem;}
[data-testid="stMetric"] {padding:10px 0;}
.stButton>button {border-radius:7px;}
[data-testid="stHeader"] {background:transparent;}
[data-testid="stImage"] img {border-radius:8px;}
[data-testid="stExpander"] {border-color:#2b3033;}
</style>''',unsafe_allow_html=True)
if HOSTED_V2:
    if 'cloud_session_id' not in st.session_state:
        st.session_state.cloud_session_id = uuid.uuid4().hex
    storage_root = ROOT/'outputs/sessions/cloud'/st.session_state.cloud_session_id
    storage_root.mkdir(parents=True, exist_ok=True)
    st.caption('Hosted V2 · CPU analysis · uploads and demos · session evidence is temporary; save clips before leaving.')
else:
    storage_root = ROOT/'outputs'

brand,status=st.columns([6,1])
with brand:
    st.title('CRASHZERO')
    st.caption('Predict Risk Before Impact')
worker=st.session_state.get('worker')
snapshot=worker.get() if worker else None
@st.fragment(run_every=1.)
def system_status():
    current=st.session_state.get('worker')
    state=current.get()['status'] if current else None
    st.caption('● AI ONLINE' if state=='MONITORING' else '○ AI READY' if (ROOT/'models/yolo11n.pt').exists() else '○ MODEL ON FIRST USE' if HOSTED_V2 else '○ MODEL MISSING')
    if current and state in ('COMPLETED','STOPPED','ERROR','DISCONNECTED') and not current.thread.is_alive():
        token=str(current.out)
        if st.session_state.get('completed_worker')!=token:
            st.session_state.completed_worker=token
            st.rerun()
with status: system_status()
page=st.radio('Navigation',['Live Analysis','Conflict Zones','Incidents'],horizontal=True,label_visibility='collapsed')

with st.expander('⚙ Camera & system'):
    a,b,c=st.columns(3)
    camera_id=a.text_input('Camera ID',value=os.environ.get('CRASHZERO_CAMERA_ID','CAM-01'))
    camera_name=b.text_input('Camera name',value=os.environ.get('CRASHZERO_CAMERA_NAME','Local camera'))
    location=c.text_input('Registered location',value=os.environ.get('CRASHZERO_CAMERA_LOCATION','LOCATION NOT CONFIGURED'))
    device=st.selectbox('Inference device',(['cpu'] if HOSTED_V2 else ['cpu','mps']),help='CPU is the verified fallback. MPS support depends on the installed PyTorch build.')
    debug=st.checkbox('Show system details')
    st.caption('Image-space estimates • no physical speed or distance claim • alerts are simulated locally.')
    if debug:
        st.write('YOLO11n · ByteTrack · temporal heuristic verification · local SQLite incidents')
        st.caption('For webcam permission: macOS System Settings → Privacy & Security → Camera → enable the app that launches Python (Terminal or Codex), then restart analysis.')

def render_status(s):
    st.caption(s['status'])
    recent_likely=bool(s.get('results') and s['results'][-1]['state'].startswith('LIKELY') and s['timestamp']-s['results'][-1].get('verified_at',0)<8)
    st.metric('LIVE RISK','CRITICAL' if recent_likely else 'HIGH' if s.get('candidates') else category(s['risk']))
    st.metric('Road users',s['road_users'])
    st.metric('Active conflicts',s['conflicts'])
    st.metric('Near misses',s['near_misses'])
    if s.get('candidates'):
        st.warning('POSSIBLE ACCIDENT · VERIFYING…')
        for e in s['candidates']:
            from config.v2 import SAFETY
            st.progress(min(1.,e['observed_seconds']/SAFETY.verification_seconds),text='Collecting temporal evidence')
            for key,value in e['evidence_signals'].items():
                if value: st.caption('✓ '+key.replace('_',' ').title())
    elif s.get('results'):
        event=s['results'][-1]
        if event['state'].startswith('LIKELY') and recent_likely:
            st.error(event['state']); st.caption('Incident created · demo alert created. Evidence status is available in Incidents.')
        elif s['timestamp']-event.get('verified_at',0)<5: st.info(event['state'])
    if s.get('message'): st.warning(s['message'])
    if debug: st.caption(f"{s['fps']:.1f} processed FPS · source {s['timestamp']:.1f}s")

@st.fragment(run_every=.5)
def monitor():
    current=st.session_state.get('worker')
    if not current: return
    s=current.get()
    left,right=st.columns([4.6,1])
    with left:
        if s['frame'] is not None: st.image(s['frame'],channels='RGB',width='stretch')
        else: st.info('Connecting source and loading the local model…')
        st.caption(f"{current.camera.name} · {current.camera.location} · {current.source_kind}")
    with right: render_status(s)
    if s['status'] in ('COMPLETED','STOPPED'): st.caption('Analysis complete. Review Conflict Zones or Incidents; select Start analysis to replay.')

if page=='Live Analysis':
    mode=st.segmented_control('SOURCE',(['UPLOAD VIDEO','DEMO'] if HOSTED_V2 else ['LIVE CAMERA','UPLOAD VIDEO','DEMO']),default='DEMO')
    source=None; fixture=None; source_kind='video'
    if mode=='LIVE CAMERA':
        camera_type=st.selectbox('Camera source',['Device webcam','IP / CCTV stream'])
        if camera_type=='Device webcam':
            index=st.number_input('Device index',0,10,0)
            source=('webcam',index)
        else:
            st.caption('Set CRASHZERO_STREAM_URL in the launching terminal. Credentials stay outside the UI and saved metadata.')
            if os.environ.get('CRASHZERO_STREAM_URL'): source=('stream',None)
            else: st.info('No IP camera configured. Set CRASHZERO_STREAM_URL and restart the app.')
        source_kind='live camera'
    elif mode=='UPLOAD VIDEO':
        uploaded=st.file_uploader('Traffic video',type=['mp4','mov','avi','mkv'])
        if uploaded:
            content=uploaded.getvalue(); folder=storage_root/'sessions/uploads';folder.mkdir(parents=True,exist_ok=True)
            path=folder/(hashlib.sha256(content).hexdigest()[:20]+Path(uploaded.name).suffix.lower())
            if not path.exists(): path.write_bytes(content)
            source=('file',path)
    else:
        choices={p.stem.replace('_',' ').title():p for p in sorted((ROOT/'data/demo').glob('*.mp4'))}
        simulations={p.stem.replace('_',' ').title()+' · SYNTHETIC TEST':p for p in sorted((ROOT/'data/simulations').glob('*.mp4'))}
        choices.update(simulations)
        if choices:
            selected=st.selectbox('Offline scenario',list(choices)); path=choices[selected]; source=('file',path)
            if 'SYNTHETIC TEST' in selected:
                fixture=path.with_suffix('.json'); source_kind='SYNTHETIC trajectory fixture — detector bypassed'
                st.warning('Synthetic engineering scenario: scripted detections test verification and evidence capture. This is not real accident footage or detector accuracy evidence.')
        else: st.info('No local demo video found. Upload a video or fetch the documented demo assets.')
    start,stop,_=st.columns([1,1,5])
    running=bool(worker and worker.thread and worker.thread.is_alive())
    if start.button('Start analysis',type='primary',disabled=not source or running):
        from src.live import AnalysisWorker
        from src.video.source import Camera,VideoFileSource,WebcamSource,StreamSource
        kind,value=source
        input_source=WebcamSource(value) if kind=='webcam' else StreamSource(os.environ['CRASHZERO_STREAM_URL']) if kind=='stream' else VideoFileSource(value)
        detector=None
        if fixture:
            from src.video.simulation import FixtureDetector
            detector=FixtureDetector(fixture)
        camera=Camera(camera_id,camera_name,location) if mode=='LIVE CAMERA' else Camera('DEMO' if mode=='DEMO' else 'UPLOAD',selected if mode=='DEMO' else 'Uploaded video')
        st.session_state.worker=AnalysisWorker(input_source,camera,device,detector=detector,source_kind=source_kind,
            store=IncidentStore(storage_root/'incidents') if HOSTED_V2 else None,
            output_dir=storage_root/'live'/uuid.uuid4().hex[:12] if HOSTED_V2 else None).start()
        st.rerun()
    if stop.button('Stop analysis',disabled=not running): worker.stop();st.rerun()
    if worker: monitor()
    else:
        left,right=st.columns([4.6,1])
        with left:
            if source and source[0]=='file': st.video(str(source[1]))
            else: st.info('Select a source and start analysis.')
            st.caption('Preview only — select Start analysis to run detection and tracking.')
        with right:
            st.markdown('**READY TO MONITOR**')
            st.caption('Anonymous road users, trajectory conflicts and temporal accident verification.')
            st.caption('Emergency dispatch: DEMO ONLY')
elif page=='Conflict Zones':
    st.subheader('Where does danger repeatedly happen?')
    sessions={}
    if snapshot and worker:
        sessions['Current analysis']={'events':snapshot.get('events',[]),'image':snapshot.get('heatmap'),'kind':worker.source_kind}
    for p in sorted((storage_root/'live').glob('*/events.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
        data=json.loads(p.read_text()); sessions[f"{data['camera']['name']} · {p.parent.name}"]={'events':data['events'],'image':str(p.parent/'heatmap.jpg'),'kind':data['source_kind']}
    cached=ROOT/'outputs/demo/analytics.json'
    if cached.exists(): sessions['V1 traffic demo · saved analysis']={'events':json.loads(cached.read_text())['events'],'image':str(cached.parent/'heatmap.jpg'),'kind':'Real traffic · saved V1 analysis'}
    if sessions:
        chosen=st.selectbox('Camera / analysis session',list(sessions)); data=sessions[chosen]
        st.caption(data['kind']+' · Image coordinates; sessions are kept separate to avoid mixing cameras.')
        if data['image'] and Path(data['image']).exists():
            import cv2
            from src.zones import draw_zone_labels
            zone_image=draw_zone_labels(cv2.imread(data['image']),data['events'])
            st.image(zone_image,channels='BGR',width='stretch')
        elif snapshot and snapshot.get('frame') is not None: st.image(snapshot['frame'],width='stretch')
        zones=conflict_zones(data['events'])
        if not zones: st.info('No accumulated conflict episodes yet.')
        for zone in zones:
            with st.expander(f"{zone['zone']} · {zone['risk']} · {zone['conflicts']} conflicts · {zone['near_misses']} near misses"):
                st.write(zone['main_interaction']);st.caption('Trend: '+zone['trend'])
                st.dataframe([{k:e.get(k) for k in ['timestamp','classes','peak_risk','status','x','y']} for e in zone['events']],hide_index=True,width='stretch')
    else: st.info('Analyze a video to accumulate conflict locations.')
else:
    st.subheader('Incidents & evidence')
    st.caption('Likely events from an unvalidated temporal heuristic. Every dispatch shown here is simulated.')
    records=(IncidentStore(storage_root/'incidents') if HOSTED_V2 else IncidentStore()).list()
    if not records: st.info('No likely accidents recorded. Normal traffic and uncertain candidates do not create dispatch records.')
    for record_index,incident in enumerate(records):
        with st.expander(f"{incident['event_type']} · {incident['incident_id']} · {incident['timestamp']:.1f}s · {incident['camera_id']}",expanded=record_index==0):
            st.caption(incident['source_kind'])
            cols=st.columns(3)
            for col,label,key in zip(cols,['BEFORE','EVENT','AFTER'],['before_path','screenshot_path','after_path']):
                with col:
                    st.caption(label)
                    if incident.get(key) and Path(incident[key]).exists():st.image(incident[key],width='stretch')
                    else: st.caption('Capturing…')
            st.write(' · '.join(f"{kind.title()} #{tid}" for kind,tid in zip(incident['road_users'],incident['track_ids'])))
            st.write(f"{incident.get('camera_name',incident.get('name','Unknown camera'))} · {incident['location']}")
            st.caption(f"Source offset {incident['timestamp']:.2f}s · Recorded {incident['created_at']} · Heuristic evidence {incident['evidence_score']:.0%} (not probability)")
            for key,value in incident['evidence_signals'].items():st.caption(('✓ ' if value else '— ')+key.replace('_',' ').title())
            st.info(incident['alert_status']+' · SIMULATED / NO EXTERNAL CONTACT')
            st.caption(incident['evidence_status'])
            if incident.get('video_clip_path') and Path(incident['video_clip_path']).exists():st.video(incident['video_clip_path'])
            if incident.get('pre_event_truncated') or incident.get('post_event_truncated'):st.caption('Partial evidence window: source started or ended close to the event.')
