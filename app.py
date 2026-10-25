"""CrashZero presentation flow; V1 remains available in app_v1.py."""
from pathlib import Path
import hashlib
import json
import os
import uuid
import streamlit as st
from config.settings import ROOT, category
from src.incidents.manager import IncidentStore
from src.zones import conflict_zones
from src.analysis_context import file_selection, camera_selection

if os.environ.get('CRASHZERO_V2_HOSTED') != '1':
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT/'.env',override=False)
    except ImportError:
        pass

HOSTED_V2 = os.environ.get('CRASHZERO_V2_HOSTED') == '1'

st.set_page_config(page_title='CrashZero · Road Safety Intelligence',page_icon='◉',layout='wide',initial_sidebar_state='collapsed')
st.markdown('<style>'+(ROOT/'assets/presentation.css').read_text()+'</style>',unsafe_allow_html=True)

MODULE_ONE='Junction Intelligence'
MODULE_TWO='Accident Response'
MODULE_TEST='TEST'
MODULE_SETTINGS='Settings'
NAV_LABELS={
    'Accident Hotspot Detector': MODULE_ONE,
    'Accident Detector & Emergency Caller': MODULE_TWO,
    'Settings': MODULE_SETTINGS,
}

def choose_module(name):
    st.session_state.cz_module=name
    st.session_state.cz_pending_nav=next((label for label,value in NAV_LABELS.items() if value==name),None)
    if name==MODULE_ONE: st.session_state.setdefault('_source_mode','UPLOAD VIDEO')
    st.rerun()

st.markdown('<div class="cz-topbar"><div class="cz-mark">✦</div><div class="cz-wordmark">Crash<em>Zero</em></div><div class="cz-tagline">AI FOR SAFER ROADS</div></div>',unsafe_allow_html=True)
if 'cz_pending_nav' in st.session_state:
    st.session_state.cz_primary_nav=st.session_state.pop('cz_pending_nav')
if 'cz_primary_nav' not in st.session_state:
    st.session_state.cz_primary_nav=next((label for label,value in NAV_LABELS.items()
                                          if value==st.session_state.get('cz_module')),None)
selected_nav=st.segmented_control('Main navigation',list(NAV_LABELS),
                                   key='cz_primary_nav',label_visibility='collapsed')
if selected_nav and NAV_LABELS[selected_nav]!=st.session_state.get('cz_module'):
    choose_module(NAV_LABELS[selected_nav])

if not st.session_state.get('cz_module'):
    st.markdown('<div class="cz-hero"><div class="cz-eyebrow">CRASHZERO · ROAD SAFETY INTELLIGENCE</div><h1>CrashZero<br><span>AI for Safer Roads</span></h1><p>Intelligent accident detection, hotspot analysis and emergency response.</p></div>',unsafe_allow_html=True)
    left,right=st.columns(2,gap='large')
    with left:
        st.markdown('<div class="cz-module"><div class="cz-module-num">01 / TRAFFIC RISK</div><h2>Accident Hotspot Detector</h2><p>Identify high-risk traffic areas using intelligent vehicle tracking and traffic analysis.</p></div>',unsafe_allow_html=True)
        if st.button('Open Hotspot Detector',type='primary',use_container_width=True):choose_module(MODULE_ONE)
    with right:
        st.markdown('<div class="cz-module"><div class="cz-module-num">02 / ACCIDENT RESPONSE</div><h2>Accident Detector & Emergency Caller</h2><p>Detect potential road accidents, verify visual evidence and initiate emergency notifications.</p></div>',unsafe_allow_html=True)
        if st.button('Open Accident Detector',use_container_width=True):choose_module(MODULE_TWO)
    st.caption('Research prototype · results require human review before emergency action.')
    st.stop()

if HOSTED_V2:
    if 'cloud_session_id' not in st.session_state:
        st.session_state.cloud_session_id = uuid.uuid4().hex
    storage_root = ROOT/'outputs/sessions/cloud'/st.session_state.cloud_session_id
    storage_root.mkdir(parents=True, exist_ok=True)
else:
    storage_root = ROOT/'outputs'

if st.session_state.cz_module==MODULE_SETTINGS:
    from src.presentation_settings import render_settings
    render_settings(storage_root,hosted=HOSTED_V2)
    st.stop()

if st.session_state.cz_module==MODULE_TWO:
    from test_lab.ui import render_test_lab
    render_test_lab(data_dir=storage_root/'test_lab' if HOSTED_V2 else None,embedded=True)
    st.stop()

if st.session_state.cz_module==MODULE_TEST:
    from test_lab.ui import render_test_lab
    render_test_lab(data_dir=storage_root/'test_lab' if HOSTED_V2 else None)
    st.stop()

if HOSTED_V2:
    st.caption('CrashZero V3 · CPU analysis · IP cameras, uploads and demos · session evidence is temporary; save clips before leaving.')

brand,status=st.columns([6,1])
with brand:
    st.title('Accident Hotspot Detector')

worker=st.session_state.get('worker')
snapshot=worker.get() if worker else None

def advance_completed(current,state):
    if (current and state['status']=='COMPLETED' and not current.source.live
            and current.thread and not current.thread.is_alive()
            and current.source_id==(st.session_state.get('selected_source') or {}).get('id')
            and st.session_state.get('cz_autonavigated_analysis')!=current.analysis_id):
        st.session_state.cz_autonavigated_analysis=current.analysis_id
        st.session_state.cz_risk_open=True
        return True
    return False

if snapshot: advance_completed(worker,snapshot)
@st.fragment(run_every=1.)
def system_status():
    current=st.session_state.get('worker')
    state=current.get()['status'] if current else None
    st.caption('● AI ONLINE' if state=='MONITORING' else '○ AI READY' if (ROOT/'models/yolo11n.pt').exists() else '○ MODEL ON FIRST USE' if HOSTED_V2 else '○ MODEL MISSING')
    if current and state=='COMPLETED' and advance_completed(current,current.get()):
        st.rerun(scope='app')
with status: system_status()
from src.ui_flow import render_flow
render_flow(['Upload / Live', 'Analyse', 'Risk Zones'],
            current=2 if snapshot and snapshot['status']=='COMPLETED' else 1 if snapshot and snapshot['status']=='MONITORING' else 0,
            completed=(0,1) if snapshot and snapshot['status']=='COMPLETED' else (0,) if snapshot and snapshot['status']=='MONITORING' else ())
page='Track vehicles'

advanced_settings=st.expander('Advanced Settings')
with advanced_settings:
    a,b,c=st.columns(3)
    camera_id=a.text_input('Camera ID',value=os.environ.get('CRASHZERO_CAMERA_ID','CAM-01'))
    camera_name=b.text_input('Camera name',value=os.environ.get('CRASHZERO_CAMERA_NAME','Local camera'))
    location=c.text_input('Registered location',value=os.environ.get('CRASHZERO_CAMERA_LOCATION','LOCATION NOT CONFIGURED'))
    device=st.selectbox('Inference device',(['cpu'] if HOSTED_V2 else ['auto','cpu','mps']),help='Auto uses an available GPU, otherwise CPU. Choose CPU to override.')
    debug=st.checkbox('Show system details')
    st.caption('Image-space estimates • no physical speed or distance claim • alerts are simulated locally.')
    if debug:
        st.write('YOLO11n · ByteTrack · temporal heuristic verification · local SQLite incidents')
        from src.ui_settings import call_settings
        call_settings(storage_root,HOSTED_V2)
        st.caption('For webcam permission: macOS System Settings → Privacy & Security → Camera → enable the app that launches Python (Terminal or Codex), then restart analysis.')

    from src.ui_settings import calibration_settings
    calibration=calibration_settings(camera_id,storage_root,HOSTED_V2)

def render_status(s):
    st.caption(s['status'])
    recent_likely=bool(s.get('results') and s['results'][-1]['state'].startswith('LIKELY') and s['timestamp']-s['results'][-1].get('verified_at',0)<8)
    risk_label='CRITICAL' if recent_likely else 'HIGH' if s.get('candidates') else category(s['risk'])
    risk_display={'LOW':('GREEN — LOW','green'),'MODERATE':('AMBER — MEDIUM','orange'),
                  'HIGH':('RED — HIGH','red'),'CRITICAL':('RED — HIGH','red')}
    label,color=risk_display.get(risk_label,('RISK UNAVAILABLE','gray'))
    st.badge(label,icon=':material/traffic:',color=color)
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
    motion=s.get('camera_motion',{})
    if motion.get('moving'): st.warning('Camera movement detected — accident confirmation withheld.')
    elif motion and not motion.get('available'): st.caption('Background motion check unavailable; confirmation withheld.')
    if s.get('results') and debug:
        st.json(s['results'][-1])
    if s.get('message'): st.warning(s['message'])
    if debug: st.caption(f"{s['fps']:.1f} processed FPS · source {s['timestamp']:.1f}s")

@st.fragment(run_every=.125)
def monitor():
    current=st.session_state.get('worker')
    if not current or getattr(current,'source_id',None)!=(st.session_state.get('selected_source') or {}).get('id'): return
    s=current.get()
    if s['status']=='COMPLETED' and advance_completed(current,s):
        st.rerun(scope='app')
    st.markdown('<div class="cz-section-label">TRACKING PREVIEW</div>',unsafe_allow_html=True)
    left,right=st.columns([1.8,1],gap='large')
    with left:
        if s['frame'] is not None: st.image(s['frame'],width='stretch')
        else: st.info('Connecting source and loading the local model…')
        st.caption(f"{current.camera.name} · {current.source_kind}")
        if current.source.live:
            st.caption('Live camera · showing the newest available frame')
            if st.button('View Key Risk Areas →',key='live_zones'):
                st.session_state.cz_risk_open=True
                st.rerun(scope='app')
        elif s.get('progress') is not None:
            st.progress(s['progress'],text=f"Analysing video · {s['progress']:.0%}")
        else:
            st.caption('Analysing video · progress is unavailable for this file')
    with right:
        st.markdown('#### Risk Analysis')
        metrics=st.columns(2)
        for column,label,value in zip(metrics,['Vehicles detected','Risk events'],
                                      [s.get('road_users',0),s.get('conflicts',0)]):
            column.metric(label,value)
        st.metric('High-risk zones',sum(z['risk']=='HIGH' for z in conflict_zones(s.get('events',[]))))
        render_status(s)
    if s['status']=='STOPPED': st.info('Analysis stopped. Start again to complete a video.')
    if s['status']=='COMPLETED': st.success('Analysis complete. Open Key Risk Areas to review the result.')

if page=='Track vehicles':
    # Durable values survive Streamlit cleaning up widgets on other screens.
    if '_source_mode' not in st.session_state:
        st.session_state['_source_mode']=st.session_state.get('source_mode','UPLOAD VIDEO')
    source_tab=st.segmented_control('Video source',['Upload Video','Live Camera'],
                                    default='Upload Video',key='m1_source_tab',
                                    label_visibility='collapsed')
    use_demo=st.toggle('Use a demo recording',key='m1_demo_recording') if source_tab=='Upload Video' else False
    mode='LIVE CAMERA' if source_tab=='Live Camera' else 'DEMO' if use_demo else 'UPLOAD VIDEO'
    st.session_state.source_mode=mode
    selection=None
    source=None; fixture=None; source_kind='video'
    if mode=='LIVE CAMERA':
        camera_type=st.selectbox('Camera source',['IP / CCTV stream'] if HOSTED_V2 else ['IP / CCTV stream','Device webcam'])
        if camera_type=='Device webcam':
            index=st.number_input('Device index',0,10,0)
            source=('webcam',index)
            selection=camera_selection(camera_id,'webcam',index)
        else:
            from src.video.stream_config import validate_stream_url
            if '_camera_stream_url' not in st.session_state:
                st.session_state['_camera_stream_url']=st.session_state.get('camera_stream_url','')
            stream_url=st.text_input('Camera stream URL',type='password',key='_camera_stream_url',
                placeholder='rtsp://username:password@camera-ip:554/stream-path',
                help='Use the RTSP video URL from your camera or NVR settings, not its web login page. Encode special characters in the username/password.')
            st.session_state.camera_stream_url=stream_url
            if not HOSTED_V2:
                stream_url=stream_url or os.environ.get('CRASHZERO_STREAM_URL','')
            st.caption('The address is used only for this session’s connection; it is not included in incident records.')
            if HOSTED_V2:
                st.info('Cloud analysis needs a reachable public IP and an RTSP/RTSPS stream. Private Wi-Fi/LAN cameras (192.168.x.x, 10.x.x.x) require CrashZero running on the same network. Your browser’s network is not the cloud server’s network.')
            else:
                st.caption('Connect this computer to the camera’s network. RTSP/RTSPS and HTTP video streams are supported. CRASHZERO_STREAM_URL is also supported.')
            if stream_url:
                try:
                    stream_url=validate_stream_url(stream_url,hosted=HOSTED_V2)
                    source=('stream',stream_url)
                    endpoint_id=hashlib.sha256(stream_url.encode()).hexdigest()
                    selection=camera_selection(camera_id,'stream',endpoint_id)
                except ValueError as exc:
                    st.warning(str(exc))
            else:
                st.info('Enter your camera’s stream URL, then select Start analysis.')
        source_kind='live camera'
    elif mode=='UPLOAD VIDEO':
        def forget_removed_upload():
            if st.session_state.get('_video_upload') is None:
                st.session_state.pop('saved_upload',None)
        uploaded=st.file_uploader('Traffic video',type=['mp4','mov','avi','mkv'],key='_video_upload',on_change=forget_removed_upload)
        if uploaded:
            content=uploaded.getvalue(); folder=storage_root/'sessions/uploads';folder.mkdir(parents=True,exist_ok=True)
            path=folder/(hashlib.sha256(content).hexdigest()[:20]+Path(uploaded.name).suffix.lower())
            if not path.exists(): path.write_bytes(content)
            st.session_state.saved_upload={'path':str(path),'name':uploaded.name}
        saved_upload=st.session_state.get('saved_upload')
        if saved_upload:
            source=('file',Path(saved_upload['path']))
            selection=file_selection(saved_upload['path'],saved_upload['name'])
            if uploaded is None:
                st.caption('Selected video: '+saved_upload['name'])
                if st.button('Clear selected video'):
                    st.session_state.pop('saved_upload',None)
                    st.rerun()
    else:
        choices={p.stem.replace('_',' ').title():p for p in sorted((ROOT/'data/demo').glob('*.mp4'))}
        simulations={p.stem.replace('_',' ').title()+' · SYNTHETIC TEST':p for p in sorted((ROOT/'data/simulations').glob('*.mp4'))}
        choices.update(simulations)
        if choices:
            if '_demo_choice' not in st.session_state:
                st.session_state['_demo_choice']=st.session_state.get('demo_choice',next(iter(choices)))
            selected=st.selectbox('Offline scenario',list(choices),key='_demo_choice')
            st.session_state.demo_choice=selected
            path=choices[selected]; source=('file',path)
            selection=file_selection(path,selected)
            if 'SYNTHETIC TEST' in selected:
                fixture=path.with_suffix('.json'); source_kind='SYNTHETIC trajectory fixture — detector bypassed'
                st.warning('Synthetic engineering scenario: scripted detections test verification and evidence capture. This is not real accident footage or detector accuracy evidence.')
        else: st.info('No local demo video found. Upload a video or fetch the documented demo assets.')
    if selection is not None:
        st.session_state.selected_source=selection
    elif not (worker and worker.thread and worker.thread.is_alive()):
        st.session_state.selected_source=None
    with advanced_settings:
        speed_mode=st.radio('Analysis quality',['Fast','Detailed'],horizontal=True,
            help='Fast uses 416 px detector input; Detailed uses 640 px and better preserves small distant road users.')
        pace_video=st.checkbox('Play at normal speed',value=False,disabled=bool(source and source[0]!='file'),
            help='Leave off to analyze files as quickly as possible. Live cameras always use the newest available frame.')
    start,stop,_=st.columns([2,1,2])
    running=bool(worker and worker.thread and worker.thread.is_alive())
    if start.button('Start analysis',type='primary',icon=':material/play_arrow:',use_container_width=True,disabled=not source or running):
        from src.live import AnalysisWorker
        from src.video.source import Camera,VideoFileSource,WebcamSource,StreamSource
        kind,value=source
        input_source=WebcamSource(value) if kind=='webcam' else StreamSource(value,hosted=HOSTED_V2) if kind=='stream' else VideoFileSource(value)
        detector=None
        if fixture:
            from src.video.simulation import FixtureDetector
            detector=FixtureDetector(fixture)
        camera=Camera(camera_id,camera_name,location) if mode=='LIVE CAMERA' else Camera('DEMO' if mode=='DEMO' else 'UPLOAD',selected if mode=='DEMO' else 'Uploaded video')
        st.session_state.worker=AnalysisWorker(input_source,camera,device,detector=detector,source_kind=source_kind,
            store=IncidentStore(storage_root/'incidents') if HOSTED_V2 else None,
            output_dir=storage_root/'live'/uuid.uuid4().hex[:12] if HOSTED_V2 else None,
            source_id=selection['id'],source_name=selection['name'],
            image_size=416 if speed_mode=='Fast' else 640,realtime=pace_video,
            **({'calibration':calibration} if calibration is not None else {})).start()
        st.session_state.setdefault('analysis_by_source',{})[selection['id']]=st.session_state.worker.analysis_id
        st.rerun()
    if stop.button('Stop analysis',icon=':material/stop:',use_container_width=True,disabled=not running): worker.stop();st.rerun()
    if worker and selection and getattr(worker,'source_id',None)==selection['id']: monitor()
    else:
        if running: st.info(f"{getattr(worker,'source_name',worker.camera.name)} is still being analyzed. Stop it before starting the selected video.")
        left,right=st.columns([1.8,1])
        with left:
            if source and source[0]=='file': st.video(str(source[1]))
            else: st.info('Select a source and start analysis.')

        with right:
            st.markdown('<div class="cz-panel"><h3>Risk Analysis</h3><p>Start analysis to see risk zones.</p></div>',unsafe_allow_html=True)
if st.toggle('Show Key Risk Areas',key='cz_risk_open',value=False):
    st.markdown('<div class="cz-section-label">ANALYSIS RESULTS</div>',unsafe_allow_html=True)
    st.subheader('Key Risk Areas')
    st.caption('See where observed traffic conflicts clustered in the selected camera view.')
    from src.intelligence_store import IntelligenceStore
    intelligence=IntelligenceStore(storage_root/'incidents' if HOSTED_V2 else ROOT/'outputs/incidents')
    sessions={}
    if snapshot and worker:
        sessions['Current analysis']={'events':snapshot.get('events',[]),'image':snapshot.get('heatmap'),
            'frame':snapshot.get('frame'),'kind':worker.source_kind,'analysis_id':worker.analysis_id}
    for p in sorted((storage_root/'live').glob('*/events.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
        data=json.loads(p.read_text()); sessions[f"{data['camera']['name']} · {p.parent.name}"]={'events':data['events'],'image':str(p.parent/'heatmap.jpg'),'kind':data['source_kind']}
    cached=ROOT/'outputs/demo/analytics.json'
    if cached.exists(): sessions['V1 traffic demo · saved analysis']={'events':json.loads(cached.read_text())['events'],'image':str(cached.parent/'heatmap.jpg'),'kind':'Real traffic · saved V1 analysis'}
    if sessions:
        chosen=st.selectbox('Camera / analysis session',list(sessions)); data=sessions[chosen]
        st.caption(data['kind']+' · Zones use coordinates in this camera image.')
        zones=conflict_zones(data['events'])
        if zones:
            st.markdown('<div class="cz-section-label">CAMERA VIEW / OBSERVED CONFLICTS</div>',unsafe_allow_html=True)
        if data['image'] and Path(data['image']).exists():
            import cv2
            from src.zones import draw_zone_labels
            zone_image=draw_zone_labels(cv2.imread(data['image']),data['events'])
            st.image(zone_image,channels='BGR',width='stretch')
        elif data.get('frame') is not None: st.image(data['frame'],width='stretch')
        if not zones: st.info('No danger spots detected in this video. Try another recording or review the tracked footage.')
        for zone in zones:
            with st.expander(f"{zone['zone']} · {zone['risk']} · {zone['conflicts']} observed conflicts · {zone['near_misses']} near misses"):
                st.write(zone['main_interaction']);st.caption('Trend: '+zone['trend'])
                st.dataframe([{k:e.get(k) for k in ['timestamp','classes','peak_risk','status','x','y']} for e in zone['events']],hide_index=True,width='stretch')
        if (chosen=='Current analysis' and worker and worker.calibration
                and worker.calibration.matrix is not None):
            persisted_hotspots=intelligence.hotspots(worker.camera.camera_id)
            if persisted_hotspots:
                st.markdown('<div class="cz-section-label">CALIBRATED ROAD MAP</div>',unsafe_allow_html=True)
                if snapshot.get('twin') is not None: st.image(snapshot['twin'],width='stretch')
                st.dataframe([{'Mapped position':tuple(round(v,3) for v in h['map_position']),
                    'Category':h['category'],'Observed events':h['count']} for h in persisted_hotspots],
                    hide_index=True,width='stretch')
        if st.button('Review incident evidence →',type='primary',key='zones_to_incidents'):
            st.session_state.cz_incidents_open=True;st.rerun()
    else: st.info('Analyze a video to accumulate conflict locations.')
if st.toggle('Show Incident Records & Saved Evidence',key='cz_incidents_open',value=False):
    @st.fragment(run_every=1.)
    def incident_timeline():
        st.subheader('Incidents & evidence')
        st.caption('Likely events from an unvalidated temporal heuristic. Test notifications only; no emergency dispatch.')
        selected_source=st.session_state.get('selected_source')
        scope=st.segmented_control('Incident scope',['Selected video','All saved incidents'],default='Selected video',
            key='incident_scope_'+(selected_source['id'] if selected_source else 'none'))
        store=IncidentStore(storage_root/'incidents') if HOSTED_V2 else IncidentStore()
        filters=st.columns(3)
        with filters[0]:
            incident_types=st.multiselect('Incident type',['LIKELY COLLISION','LIKELY_ACCIDENT','NEAR_MISS','POSSIBLE_ACCIDENT','UNCERTAIN'])
        with filters[1]:
            incident_statuses=st.multiselect('Verification status',['LIKELY COLLISION','LIKELY_ACCIDENT','NEAR_MISS','POSSIBLE_ACCIDENT','UNCERTAIN'])
        with filters[2]:
            date_range=st.date_input('Recorded date range',value=(),key='incident_dates')
        start_date=end_date=None
        if isinstance(date_range,(tuple,list)) and len(date_range)==2:
            start_date,end_date=date_range
        if scope=='All saved incidents':
            records=store.list(start_date=start_date,end_date=end_date,event_types=incident_types,statuses=incident_statuses)
            st.caption('All saved analyses, including older records without video information.')
        else:
            analysis_id=st.session_state.get('analysis_by_source',{}).get(selected_source['id']) if selected_source else None
            records=store.list(analysis_id=analysis_id,start_date=start_date,end_date=end_date,
                               event_types=incident_types,statuses=incident_statuses) if analysis_id else []
            if selected_source: st.caption('Selected video: '+selected_source['name'])
            if not analysis_id:
                st.info('Start analysis for the selected video to see its incidents.' if selected_source else 'Select a video in Live Analysis first.')
                return
        if not records: st.info('No likely accidents recorded for this analysis.' if scope=='Selected video' else 'No saved incidents.')
        for record_index,incident in enumerate(records):
            with st.expander(f"{incident['event_type']} · {incident['incident_id']} · {incident['timestamp']:.1f}s · {incident['camera_id']}",expanded=record_index==0):
                st.caption(incident.get('source_name') or 'Older recording · source not recorded')
                st.caption(incident['source_kind'])
                cols=st.columns(3)
                for col,label,key in zip(cols,['BEFORE','EVENT','AFTER'],['before_path','screenshot_path','after_path']):
                    with col:
                        st.caption(label)
                        image=store.get_screenshot(incident['incident_id']) if key=='screenshot_path' else None
                        if image: st.image(image,width='stretch')
                        elif incident.get(key) and Path(incident[key]).exists():st.image(incident[key],width='stretch')
                        else: st.caption('Capturing…')
                st.write(' · '.join(f"{kind.title()} #{tid}" for kind,tid in zip(incident['road_users'],incident['track_ids'])))
                st.write(f"{incident.get('camera_name',incident.get('name','Unknown camera'))} · {incident.get('location',incident.get('registered_location','Location not configured'))}")
                st.caption(f"Source offset {incident['timestamp']:.2f}s · Recorded {incident['created_at']} · Heuristic evidence {incident['evidence_score']:.0%} (not probability)")
                for key,value in incident['evidence_signals'].items():st.caption(('✓ ' if value else '— ')+key.replace('_',' ').title())
                from src.alerts.service import AlertService
                ledger=AlertService(storage_root/'incidents/calls' if HOSTED_V2 else None).store
                eligibility=ledger.eligibility(incident['incident_id'])
                if eligibility:
                    st.info('Call eligibility: '+('PASSED' if eligibility['passed'] else 'WITHHELD'))
                    for reason in eligibility['reasons']: st.caption(reason)
                for attempt in ledger.list(incident['incident_id']):
                    st.caption(f"Test call · {attempt['provider']} · {attempt['status']}")
                if not eligibility: st.caption('Call eligibility pending evidence finalization.')
                st.caption(incident['evidence_status'])
                clip=store.get_clip(incident['incident_id'])
                if clip:
                    st.video(clip)
                    st.download_button('Download incident clip',clip,file_name=f"{incident['incident_id']}.mp4",
                                       mime='video/mp4',key='download_'+incident['incident_id'])
                elif incident.get('video_clip_path') and Path(incident['video_clip_path']).exists():
                    st.video(incident['video_clip_path'])
                if incident.get('pre_event_truncated') or incident.get('post_event_truncated'):st.caption('Partial evidence window: source started or ended close to the event.')
    incident_timeline()
