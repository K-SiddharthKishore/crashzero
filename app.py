from pathlib import Path
import html, json, hashlib, datetime, os
HOSTED = os.environ.get("CRASHZERO_HOSTED")=="1"
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from config.settings import ROOT, COLORS, category, DEFAULT_WEIGHTS
from src.historical import load_history, grid_hotspots, historical_index
from src.prediction import load_or_train, timeline
from src.fusion import fuse
from src.hotspots import emerging_status

st.set_page_config(page_title='CrashZero · Road Safety Intelligence',page_icon='◉',layout='wide')
st.markdown('<style>'+ (ROOT/'assets/style.css').read_text()+'</style>',unsafe_allow_html=True)
@st.cache_data
def history(): return load_history()
@st.cache_resource
def predictor(): return load_or_train(history())

def card(label,value,sub='',color='#edf3fc'):
    st.markdown(f'<div class="card"><div class="label">{html.escape(label)}</div><div class="value" style="color:{color}">{html.escape(str(value))}</div><div class="sub">{html.escape(sub)}</div></div>',unsafe_allow_html=True)
def section(s): st.markdown(f'<div class="section">{s}</div>',unsafe_allow_html=True)
def chart(fig,height=300):
    fig.update_layout(template='plotly_dark',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(family='Arial',color='#9fb0c7',size=12),height=height,margin=dict(l=8,r=12,t=28,b=20),colorway=['#67e8b5','#83baff','#f6cf6b','#ff985b','#ff5d78'],legend_title_text='')
    fig.update_xaxes(gridcolor='#1c2b3d');fig.update_yaxes(gridcolor='#1c2b3d')
    st.plotly_chart(fig,width='stretch',config={'displayModeBar':False})
def evidence(): st.caption('REAL PUBLIC DATA · NYC 2024 · Prototype / demonstration dataset · Not Bengaluru accident history')
def session():
    out=Path(st.session_state.get('analysis_dir',ROOT/'outputs/demo'))
    p=out/'analytics.json'
    return (json.loads(p.read_text()),out) if p.exists() else (None,out)
def video_metrics(s):
    cols=st.columns(5)
    for c,(label,val,sub) in zip(cols,[('Road users tracked',s['road_users'],'Temporary IDs; fragmentation possible'),('Near misses',s['near_misses'],'Prototype candidates'),('High-risk episodes',s['high_interactions'],'Deduplicated pair interactions'),('Peak interaction',s['peak_risk'],'Highest pair score / 100'),('Live clip index',s['live_risk'],'90th percentile frame risk / 100')]):
        with c: card(label,val,sub,COLORS.get(category(float(val))) if 'index' in label or 'Peak' in label else '#edf3fc')
def render_video(s,out):
    st.video(str(out/'processed.mp4'))
    st.caption(f"Preprocessed playback · {s['duration']} sec analyzed · {s['frames_analyzed']} frames · {s['throughput_fps']} inference FPS on {s['device'].upper()} · dashed paths project 2.5 seconds")

def geo_plot(d,color='score',size='crashes',title='Spatial concentration'):
    if d.empty: st.info('No geocoded records match these filters.'); return
    fig=px.scatter(d,x='longitude',y='latitude',color=color,size=size,size_max=24,hover_data=[c for c in ['crashes','injuries','score','borough'] if c in d],color_continuous_scale=['#67e8b5','#f6cf6b','#ff985b','#ff5d78'],range_color=[0,100],title=title)
    if title=='Predicted injury context': fig.update_traces(marker_symbol='diamond')
    fig.update_yaxes(scaleanchor='x',scaleratio=1.32)
    chart(fig,480)
    st.caption('Offline geographic view · WGS84 longitude / latitude · scroll to zoom, drag to inspect. No online map tiles required.')

with st.sidebar:
    st.markdown('<div class="brand">CRASH<span>ZERO</span></div><div class="muted">Predict Risk Before Impact</div><div class="line"></div>',unsafe_allow_html=True)
    page=st.radio('INTELLIGENCE WORKSPACE',['Overview','City Risk','Historical Analysis','Future Prediction','Live CCTV','Near Misses','Risk Hotspots','About'],label_visibility='collapsed')
    st.markdown('<div class="line"></div><div class="eyebrow">SYSTEM STATUS</div><span class="pill">'+('CACHED CLOUD DEMO' if HOSTED else '● LOCAL ENGINE')+'</span><span class="pill">DEMO READY</span>',unsafe_allow_html=True)
    st.caption('YOLO11n · ByteTrack\n\nAnonymous road-user tracking. No face or plate recognition.')
    st.caption('RESEARCH PROTOTYPE · v1.0')
    saved=sorted((ROOT/'outputs/sessions').glob('*/analytics.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    if saved:
        with st.expander('Saved video sessions'):
            selected=st.selectbox('Session',saved,format_func=lambda p: p.parent.name)
            if st.button('Restore session'):
                st.session_state.analysis_dir=str(selected.parent); st.session_state.analysis_kind='Saved local analysis'; st.rerun()

s,out=session(); df=history()
if df.empty and page in ['City Risk','Historical Analysis','Future Prediction']:
    st.warning('Historical dataset unavailable. Run scripts/fetch_data.py online once. Video intelligence remains available.'); st.stop()

if page=='Overview':
    st.markdown('<div class="hero"><div class="eyebrow">ROAD SAFETY INTELLIGENCE / COMMAND CENTER</div><h1>See the risk. Before the impact.</h1><p>Historical evidence. Live trajectories. Forward-looking intelligence.</p><div class="quote">“We don’t want a crash to be the first data point telling us that an intersection is dangerous.”</div></div>',unsafe_allow_html=True)
    scope=st.segmented_control('Evidence scope',['Active camera','NYC historical context'],default='Active camera')
    if scope=='Active camera':
        live=s['live_risk'] if s else None; fused=fuse(live=live)
        vals=[('Dynamic risk',fused['score'],'Available-source index · live only'),('Historical risk','—','Camera location is unverified'),('Predicted risk','—','No matched historical model'),('Live risk',live,'Clip index · 90th percentile')]
    else:
        borough=st.selectbox('NYC borough',sorted(df[df.borough!='UNKNOWN'].borough.unique()))
        model,metrics=predictor(); tl=timeline(model,borough,0,'SEDAN'); hist=historical_index(df,borough); pred=float(tl.score.mean()); fused=fuse(historical=hist,predictive=pred)
        vals=[('Dynamic risk',fused['score'],'Historical + conditional injury index'),('Historical risk',hist,'Relative reported crash count / borough'),('Predicted risk',round(pred,1),'Mean modeled injury likelihood × 100'),('Live risk','—','No verified CCTV at this location')]
    cols=st.columns(4)
    for c,(label,val,sub) in zip(cols,vals):
        with c: card(label,'—' if val is None else val,sub,COLORS.get(category(val),'#edf3fc') if isinstance(val,(int,float)) else '#60748f')
    left,right=st.columns([1.65,1])
    with left:
        section('Live vision / active camera')
        if s:
            st.image(str(out/'preview.jpg'),width='stretch')
            st.caption('REAL VIDEO · Cached algorithm output · Camera location unverified · No confirmed collision claim')
        else: st.info('Open Live CCTV to analyze a video.')
    with right:
        section('Evidence behind the score')
        if scope=='Active camera' and s:
            st.write(f"**{s['high_interactions']}** distinct high-risk interactions in **{s['duration']} seconds**.")
            st.write(f"**{s['near_misses']}** interactions separated without observed bounding-box overlap; these are prototype near-miss candidates.")
            if s['conflict_types']:
                top=max(s['conflict_types'],key=s['conflict_types'].get); st.write(f"Most frequent interaction: **{top}**.")
            st.write(f"Peak pair risk **{s['peak_risk']}/100**; last analyzed frame **{s['current_risk']}/100**.")
            st.caption(emerging_status(s)['reason'])
        else:
            st.write('The index combines reported crash volume and modeled injury severity context. It is not a probability that a crash will occur.')
            st.caption('Scenario: Monday, sedan involvement, mean of 24 hourly injury estimates. Historical volume is not exposure-adjusted.')
        st.caption('Missing sources are excluded and remaining weights are normalized.')
        for k,v in fused['weights'].items(): st.write(f'{k.title()} weight **{v:.0%}**')
    if s:
        cols=st.columns(4)
        for c,(l,v,sub) in zip(cols,[('Near misses',s['near_misses'],'Prototype candidates'),('Critical interactions',s['critical_interactions'],'Peak score ≥81'),('Road users tracked',s['road_users'],'Temporary anonymous IDs'),('Historical peak hour',f'{int(df.hour.value_counts().idxmax()):02d}:00' if not df.empty else '—','NYC 2024 · crash count, not exposure')]):
            with c: card(l,v,sub)
    section('Three perspectives. One safety question.')
    for c,(a,b) in zip(st.columns(3),[('01 / PAST','Find concentration in real police-reported crash records.'),('02 / PRESENT','Measure converging trajectories and short-horizon conflicts.'),('03 / FUTURE','Explore context-dependent injury estimates with an evaluated model.')]):
        with c: st.markdown(f'**{a}**\n\n{b}')

elif page=='Live CCTV':
    st.title('Live traffic intelligence'); st.caption('Analyze a local clip with YOLO11n + ByteTrack. Processing runs on this Mac; playback uses the completed analysis.' if not HOSTED else 'Hosted demonstration: cached local analysis. Uploads and inference are available in the local version.')
    mode=st.radio('Video source',['Use demo video'] if HOSTED else ['Use demo video','Upload video'],horizontal=True)
    source=ROOT/'data/demo/traffic.mp4'
    if mode=='Use demo video' and not HOSTED:
        demo_choice=st.selectbox('Demo scene',['City intersection','Mixed traffic / motorcycles','Highway traffic'])
        source=ROOT/'data/demo'/({'City intersection':'traffic.mp4','Mixed traffic / motorcycles':'mixed_traffic.mp4','Highway traffic':'highway.mp4'}[demo_choice])
    if mode=='Upload video':
        uploaded=st.file_uploader('Traffic footage · MP4 / MOV / AVI',type=['mp4','mov','avi'])
        if uploaded is not None:
            content=uploaded.getvalue(); digest=hashlib.sha256(content).hexdigest()[:16]
            target=ROOT/'outputs/sessions'/digest; target.mkdir(parents=True,exist_ok=True)
            source=target/('input'+Path(uploaded.name).suffix.lower()); source.write_bytes(content)
        else: source=None
    a,b,c=st.columns([1,1,2])
    with a: duration=st.slider('Maximum seconds to analyze',5,120,35,5)
    with b: device=st.selectbox('Inference device',['cpu','mps'],help='CPU is verified on this Mac. MPS uses Apple Metal when available.')
    with c: st.caption('Fixed camera recommended. Moving cameras, shadows, occlusion and perspective can produce false alerts. No measured km/h or metres.')
    if st.button('Analyze video',type='primary',disabled=source is None or HOSTED):
        from src.video_processor import process_video
        key=hashlib.sha256(source.read_bytes()).hexdigest()[:12]+f'-{duration}-{device}'
        dest=ROOT/'outputs/sessions'/key
        progress=st.progress(0.,text='Loading local detector…')
        try:
            summary=process_video(source,dest,device=device,max_seconds=duration,progress=lambda p,n,r:progress.progress(p,text=f'{n} frames analyzed · current pair risk {r}/100'))
            st.session_state.analysis_dir=str(dest); st.session_state.analysis_kind='Fresh local analysis'; st.rerun()
        except Exception as e: st.error(f'Analysis could not complete: {e}')
    if st.button('Load offline demo analytics'):
        st.session_state.analysis_dir=str(ROOT/'outputs/demo'); st.session_state.analysis_kind='Cached demo analysis'; st.rerun()
    s,out=session()
    if s:
        st.markdown(f"**{st.session_state.get('analysis_kind','Cached demo analysis')}** · {s['evidence']}")
        video_metrics(s)
        l,r=st.columns([2,1])
        with l: render_video(s,out)
        with r:
            section('What the engine observed')
            st.write(f"**{s['critical_interactions']}** critical interactions")
            st.write(f"**{s['current_risk']}/100** at the last frame")
            st.write(f"**{s['duration']} sec** analyzed")
            st.write(f"**{s['analysis_fps']} FPS** sampling rate")
            st.caption(s['risk_definition'])
            st.download_button('Download processed video',(out/'processed.mp4').read_bytes(),'crashzero_processed.mp4','video/mp4')
            st.download_button('Export analytics JSON',(out/'analytics.json').read_bytes(),'crashzero_analytics.json','application/json')
            st.download_button('Export tracks CSV',(out/'tracks.csv').read_bytes(),'crashzero_tracks.csv','text/csv')
        chart(px.area(pd.DataFrame(s['timeline']),x='timestamp',y='risk',labels={'timestamp':'Video time (seconds)','risk':'Pair risk / 100'},color_discrete_sequence=['#67e8b5']))
        if s['truncated']: st.info('Analysis stopped at the selected duration limit. The remainder was not analyzed.')

elif page=='Historical Analysis':
    st.title('Historical accident intelligence'); evidence()
    a,b,c=st.columns(3)
    with a: borough=st.selectbox('Borough',['All']+sorted(df.borough.unique()))
    with b: dates=st.date_input('Date range',(df.date.min().date(),df.date.max().date()),min_value=df.date.min().date(),max_value=df.date.max().date())
    with c: vehicle=st.selectbox('Primary vehicle',['All']+sorted(df.vehicle.unique()))
    d=df.copy()
    if borough!='All': d=d[d.borough==borough]
    if vehicle!='All': d=d[d.vehicle==vehicle]
    if len(dates)==2: d=d[d.date.between(pd.Timestamp(dates[0]),pd.Timestamp(dates[1]))]
    if d.empty: st.info('No crashes match these filters.'); st.stop()
    for col,(label,val) in zip(st.columns(4),[('Reported crashes',len(d)),('Injury crashes',int(d.injury.sum())),('Fatal crashes',int((d.severity=='Fatal').sum())),('Map coverage',f'{d.geo_valid.mean():.0%}')]):
        with col: card(label,f'{val:,}' if isinstance(val,int) else val,'Within selected records')
    left,right=st.columns(2)
    with left:
        section('When / reported crash concentration')
        chart(px.bar(d.groupby('hour').size().reset_index(name='Crashes'),x='hour',y='Crashes',color_discrete_sequence=['#67e8b5']))
        section('Trend / daily crash reports')
        chart(px.line(d.groupby('date').size().reset_index(name='Crashes'),x='date',y='Crashes'))
        section('Day of week')
        days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        chart(px.bar(d.groupby('day').size().reindex(days,fill_value=0).reset_index(name='Crashes'),x='day',y='Crashes'))
    with right:
        section('Consequences / reported severity')
        chart(px.pie(d,names='severity',hole=.65,color='severity',color_discrete_map={'Fatal':'#ff5d78','Injury':'#ff985b','No injury reported':'#67e8b5'}))
        section('Road users / primary vehicle')
        chart(px.bar(d.vehicle.value_counts().head(8).rename_axis('Vehicle').reset_index(name='Crashes'),y='Vehicle',x='Crashes',orientation='h'))
        section('Severity by hour')
        chart(px.histogram(d,x='hour',color='severity',barmode='stack',color_discrete_map={'Fatal':'#ff5d78','Injury':'#ff985b','No injury reported':'#67e8b5'}))
    st.info('Counts describe reported incidents, not risk per trip. Weather, lighting, road surface and junction type are unavailable in this dataset; no relationships are invented.')
    st.download_button('Export filtered history',d.to_csv(index=False).encode(),'crashzero_history.csv','text/csv')

elif page=='Future Prediction':
    st.title('Future risk / context explorer'); evidence()
    st.info('This model estimates injury likelihood GIVEN a reported crash. It cannot estimate whether a crash will happen. The timeline applies historical relationships to a selected future context.')
    model,metrics=predictor()
    a,b,c=st.columns(3)
    with a: borough=st.selectbox('Location / borough',sorted(df[df.borough!='UNKNOWN'].borough.unique()))
    with b: date=st.date_input('Scenario date',datetime.date.today()+datetime.timedelta(days=1),key='future_date')
    with c: vehicle=st.selectbox('Vehicle context',sorted(df.vehicle.unique()),index=list(sorted(df.vehicle.unique())).index('SEDAN'))
    tl=timeline(model,borough,date.weekday(),vehicle)
    peak=tl.loc[tl.score.idxmax()]; average=float(tl.score.mean()); hist=historical_index(df,borough)
    a,b,c=st.columns(3)
    with a: card('Peak conditional injury index',f'{peak.score:.1f}/100',f"{int(peak.hour):02d}:00–{int(peak.hour)+1:02d}:00 · {peak.category}",COLORS[peak.category])
    with b: card('Daily mean index',f'{average:.1f}/100','Mean of 24 modeled hourly contexts')
    with c: card('Temporal holdout AUC',metrics['roc_auc'],'Oct–Dec 2024 · injury classification')
    chart(px.line(tl,x='hour',y='score',markers=True,labels={'hour':'Hour in selected local context','score':'Conditional injury estimate × 100'}),330)
    blocks=tl.groupby(tl.hour//2).agg(score=('score','mean')).reset_index()
    blocks['Window']=blocks.hour.map(lambda h:f'{h*2:02d}:00–{h*2+2:02d}:00');blocks['Category']=blocks.score.map(category)
    st.dataframe(blocks[['Window','score','Category']].rename(columns={'score':'Injury index / 100'}),hide_index=True,width='stretch')
    l,r=st.columns(2)
    with l:
        section('Evidence and explanation')
        subset=df[(df.borough==borough)&(df.weekday==date.weekday())&(df.vehicle==vehicle)]
        st.write(f'Context: **{borough.title()} · {date.strftime("%A")} · {vehicle.title()}**')
        st.write(f'**{len(subset):,}** matching crash records in the full dataset; observed injury share **{subset.injury.mean():.1%}**.' if len(subset) else 'No exact matching historical records; this context has weak support.')
        st.caption('The classifier uses borough, hour, weekday and vehicle context. Historical frequency, injury totals and post-crash contributing factors are excluded from model inputs. These associations do not establish causation.')
        st.json(metrics,expanded=False)
    with r:
        section('Transparent dynamic fusion')
        st.caption('Composite safety-priority index; component meanings differ. Not a calibrated probability. No location-matched live source is available.')
        wh=st.slider('Historical weight',0,100,25); wp=st.slider('Predictive weight',0,100,30)
        f=fuse(hist,average,None,{'historical':wh,'predictive':wp,'live':0})
        card('Dynamic context index',f['score'] if f['score'] is not None else '—','Weights normalized across available sources')
        st.json(f,expanded=False)
    st.download_button('Export hourly predictions',tl.to_csv(index=False).encode(),'crashzero_predictions.csv','text/csv')

elif page=='City Risk':
    st.title('City risk / spatial evidence'); evidence()
    a,b,c=st.columns(3)
    with a: layer=st.selectbox('Evidence layer',['Historical density','Historical severity','Predicted injury context','Emerging hotspots'])
    with b: hours=st.slider('Hour range',0,23,(0,23))
    with c: severity=st.multiselect('Severity',sorted(df.severity.unique()),default=sorted(df.severity.unique()))
    a,b=st.columns(2)
    with a: dates=st.date_input('Map date range',(df.date.min().date(),df.date.max().date()),key='map_date')
    with b: vehicle=st.selectbox('Map vehicle',['All']+sorted(df.vehicle.unique()))
    d=df[df.hour.between(*hours)&df.severity.isin(severity)].copy()
    if len(dates)==2:d=d[d.date.between(pd.Timestamp(dates[0]),pd.Timestamp(dates[1]))]
    if vehicle!='All':d=d[d.vehicle==vehicle]
    st.markdown('<span class="pill">LOW 0–30</span><span class="pill" style="color:#f6cf6b">MODERATE 31–60</span><span class="pill" style="color:#ff985b">HIGH 61–80</span><span class="pill" style="color:#ff5d78">CRITICAL 81–100</span>',unsafe_allow_html=True)
    if layer=='Emerging hotspots':
        st.info('No verified geographic link exists between the demo camera and NYC crash history. No emerging city markers can be asserted. View Risk Hotspots for measured image-space conflict zones.')
    else:
        grid=grid_hotspots(d)
        if layer=='Historical severity' and not grid.empty:
            grid['score']=100*grid.injuries/grid.crashes
            st.caption('Color = observed injury-crash share; small samples are unstable. Size = reported crash count.')
        elif layer=='Predicted injury context':
            model,_=predictor()
            grid=d[d.geo_valid&(d.borough!='UNKNOWN')].groupby('borough').agg(latitude=('latitude','median'),longitude=('longitude','median'),crashes=('collision_id','count')).reset_index()
            grid['score']=[float(timeline(model,b,0,'SEDAN').query('@hours[0] <= hour <= @hours[1]').score.mean()) for b in grid.borough]
            st.caption('Borough centroid diamonds · Monday / sedan conditional injury model · selected hours. These are model context markers, not predicted crash locations.')
        else: st.caption('Color = log-scaled crash count relative to the busiest ~1 km grid cell. Size = count. These are concentration indices, not probabilities.')
        geo_plot(grid,title=layer)
        if st.toggle('Show online street basemap (requires internet)') and not grid.empty:
            import pydeck as pdk
            grid['color']=grid.score.map(lambda x:[int(COLORS[category(x)].lstrip('#')[i:i+2],16) for i in (0,2,4)])
            deck=pdk.Deck(layers=[pdk.Layer('ScatterplotLayer',grid,get_position='[longitude,latitude]',get_fill_color='color',get_radius=240,pickable=True)],initial_view_state=pdk.ViewState(latitude=40.73,longitude=-73.95,zoom=10),map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',tooltip={'text':'Score: {score}\nCrashes: {crashes}'})
            st.pydeck_chart(deck)
        st.dataframe(grid.sort_values('score',ascending=False).head(20),hide_index=True,width='stretch')

elif page in ['Near Misses','Risk Hotspots']:
    st.title('Near-miss intelligence' if page=='Near Misses' else 'Risk hotspots / camera space')
    if not s: st.info('Analyze a video in Live CCTV first.'); st.stop()
    st.caption(f"Session {s['session_id']} · Stored analysis · Anonymous temporary IDs")
    if page=='Near Misses':
        video_metrics(s)
        status=st.selectbox('Event status',['All','prototype near miss','overlap / review','unresolved / track lost','unresolved / clip ended'])
        events=pd.DataFrame(s['events'])
        if not events.empty:
            if status!='All':events=events[events.status==status]
            st.dataframe(events,hide_index=True,width='stretch')
        else: st.info('No high-risk episodes met the threshold in this clip. No events have been fabricated.')
        st.caption('Near miss = a high-risk episode followed by ≥0.5 seconds of visible separation, with no observed 2D box overlap during the episode. Overlap means review, not a confirmed collision. Lost tracks and clip endings remain unresolved. Each pair has a 3-second cooldown.')
        st.download_button('Export all event records',(out/'events.csv').read_bytes(),'crashzero_events.csv','text/csv')
        section('Review the source'); render_video(s,out)
    else:
        l,r=st.columns([1.7,1])
        with l:
            st.image(str(out/'heatmap.jpg'),width='stretch')
            st.caption('One location per deduplicated high-risk episode · Gaussian density in image pixels · green/yellow/orange/red indicates increasing relative density; not city coordinates.')
            if not s['events']: st.info('No conflict locations to accumulate; source frame is shown without a heat overlay.')
        with r:
            emerging=emerging_status(s)
            section(emerging['status']);st.write(emerging['reason'])
            st.write(f"Risk trend: **{'increasing' if emerging['increasing'] else 'not increasing'}**")
            st.caption(f"Mean high-risk pairs/frame: first half {emerging['early_rate']:.2f}; second half {emerging['late_rate']:.2f}.")
            card('Distinct conflict episodes',s['high_interactions'],'Counts include unresolved and overlap/review episodes')
            if s['events']:
                zones={}
                for e in s['events']:
                    if 0<=e['x']<s['width'] and 0<=e['y']<s['height']:
                        key=(min(2,int(e['x']/s['width']*3)),min(2,int(e['y']/s['height']*3)));zones[key]=zones.get(key,0)+1
                if zones:
                    z=max(zones,key=zones.get);st.write(f"Most repeated zone: **{['top','middle','bottom'][z[1]]} {['left','center','right'][z[0]]}** ({zones[z]} episodes)")
        if s['conflict_types']:
            types=pd.DataFrame(s['conflict_types'].items(),columns=['Interaction','Episodes']); types['Share']=types.Episodes/types.Episodes.sum()*100
            section('High-risk interaction types'); chart(px.bar(types,x='Interaction',y='Episodes',text=types.Share.map(lambda x:f'{x:.0f}%')))
        st.download_button('Export heatmap',(out/'heatmap.jpg').read_bytes(),'crashzero_heatmap.jpg','image/jpeg')

elif page=='About':
    st.title('Before a crash becomes a data point.')
    st.write('CrashZero combines historical analysis, computer vision and transparent risk indicators to support earlier investigation of road-safety concerns.')
    for c,(title,body) in zip(st.columns(3),[('PAST','NYC police-reported collisions → cleaning → hourly patterns → spatial concentration.'),('PRESENT','YOLO11n → ByteTrack → image-space motion → 2.5-second closest approach → episode review.'),('FUTURE','Random forest → conditional injury context → hourly scenario timeline → available-source fusion.')]):
        with c: st.markdown(f'### {title}\n{body}')
    section('Data provenance')
    st.json(json.loads((ROOT/'data/historical/source.json').read_text()),expanded=True)
    if (ROOT/'data/demo/source.json').exists():st.json(json.loads((ROOT/'data/demo/source.json').read_text()),expanded=True)
    section('Risk formula')
    st.code('pair risk = 100 × (0.40 proximity + 0.30 urgency + 0.20 convergence + 0.10 vulnerable-user)\n            × (0.55 + 0.45 trajectory confidence)\nclip index = 90th percentile of frame maximum pair risks\ndynamic index = sum(available score × normalized source weight)')
    st.caption('Proximity = 1 − projected separation / (1.4 × combined box-based radius). Urgency = 1 − estimated time / 2.5 sec. Convergence normalized by combined radius. Components clipped to [0,1]. Thresholds: ≤30 low, ≤60 moderate, ≤80 high, >80 critical. Heuristic, uncalibrated categories.')
    section('Privacy and limitations')
    st.write('Processing and uploaded videos stay in the local project. IDs are temporary, per analysis; no facial recognition, identity matching or license-plate recognition. Original footage can still contain identifiable people and vehicles. Delete outputs/sessions to remove uploads; events are stored in outputs/events.sqlite.')
    st.write('Perspective, camera motion, occlusion, acceleration, turns, missed detections and ID switches limit image-space estimates. 2D overlap cannot establish a collision. No ground truth validates the conflict score. The ML model predicts injury conditional on a reported crash, not occurrence. Missing historical coverage never means zero crashes.')
    section('Future scope')
    st.write('Camera calibration, road geometry, signal phases, traffic exposure, weather context, multi-camera fusion, edge inference, trajectory Transformers, spatio-temporal GNNs and independently labeled evaluation.')
    st.download_button('Hackathon pitch & judge Q&A',(ROOT/'HACKATHON_NOTES.md').read_bytes(),'HACKATHON_NOTES.md','text/markdown')

st.markdown('<div class="footer">CrashZero is a hackathon research prototype. Its risk estimates are not certified collision predictions and should not be used as a standalone traffic-control or safety system.</div>',unsafe_allow_html=True)
