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

st.set_page_config(page_title='CrashZero · Predict Risk Before Impact',page_icon='◉',layout='wide')
st.markdown('<style>'+ (ROOT/'assets/style.css').read_text()+'</style>',unsafe_allow_html=True)
@st.cache_data
def history(): return load_history()
@st.cache_resource
def predictor(): return load_or_train(history())

# ---------- presentation helpers (styling only — no data/logic here) ----------
def esc(x): return html.escape(str(x))
def tip(text): return f'<span class="info-dot" title="{esc(text)}">i</span>'

def badge(cat):
    cat = cat if cat in ('LOW','MODERATE','HIGH','CRITICAL','NEUTRAL') else 'UNAVAILABLE'
    return f'<span class="badge {cat}"><span class="dot"></span>{cat}</span>'

def meter(score):
    pct=max(0,min(100,float(score)))
    return (f'<div class="meter"><div class="meter-track"><div class="meter-marker" style="left:calc({pct}% - 1.5px)"></div></div>'
            f'<div class="meter-labels"><span>Low</span><span>Moderate</span><span>High</span><span>Critical</span></div></div>')

def card(label,value,sub='',color='var(--text)',primary=False,score=None):
    cls='card primary' if primary else 'card'
    extra=f'<div style="margin:8px 0 2px">{badge(category(score))}</div>{meter(score)}' if (primary and score is not None) else ''
    st.markdown(f'<div class="{cls}"><div class="label">{esc(label)}</div><div class="value" style="color:{color}">{esc(value)}</div>{extra}<div class="sub">{esc(sub)}</div></div>',unsafe_allow_html=True)

def section(title,sub=None,tip_text=None):
    t=f' {tip(tip_text)}' if tip_text else ''
    st.markdown(f'<div class="section">{esc(title)}{t}</div>'+(f'<div class="section-sub">{esc(sub)}</div>' if sub else ''),unsafe_allow_html=True)

def page_header(title,subtitle=None):
    st.title(title)
    if subtitle: st.markdown(f'<p style="color:var(--text-secondary);margin:-10px 0 18px;font-size:14.5px;max-width:680px">{esc(subtitle)}</p>',unsafe_allow_html=True)

def empty_state(title,body,glyph='—'):
    st.markdown(f'<div class="empty-state"><div class="glyph">{esc(glyph)}</div><h4>{esc(title)}</h4><p>{esc(body)}</p></div>',unsafe_allow_html=True)

def chart(fig,height=300):
    fig.update_layout(template='plotly_dark',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(family='-apple-system,Segoe UI,Arial',color='#9aa4b2',size=12),height=height,margin=dict(l=8,r=12,t=28,b=20),colorway=['#67e8b5','#83baff','#f6cf6b','#ff985b','#ff5d78'],legend_title_text='')
    fig.update_xaxes(gridcolor='rgba(255,255,255,.06)',zeroline=False);fig.update_yaxes(gridcolor='rgba(255,255,255,.06)',zeroline=False)
    st.plotly_chart(fig,width='stretch',config={'displayModeBar':False})
def threshold_lines(fig):
    for y,c in [(30,'#f6cf6b'),(60,'#ff985b'),(80,'#ff5d78')]: fig.add_hline(y=y,line_dash='dot',line_width=1,line_color=c,opacity=.45)
    return fig
def evidence(): st.caption('REAL PUBLIC DATA · NYC 2024 · Prototype / demonstration dataset · Not Bengaluru accident history')

def stat_row(items):
    st.markdown('<div class="chip-row">'+''.join(f'<span class="chip"><b>{esc(v)}</b> {esc(l)}</span>' for v,l in items)+'</div>',unsafe_allow_html=True)
def weight_bar(weights):
    if not weights: return
    palette={'historical':'#83baff','predictive':'#67e8b5','live':'#f6cf6b'}
    segs=''.join(f'<div style="flex:{v};background:{palette.get(k,"var(--accent)")}"></div>' for k,v in weights.items())
    labels=''.join(f'<span><b>{v:.0%}</b>&nbsp;{esc(k.title())}</span>' for k,v in weights.items())
    st.markdown(f'<div class="weight-bar">{segs}</div><div class="weight-labels">{labels}</div>',unsafe_allow_html=True)

def fmt_time(sec):
    sec=int(sec); return f'{sec//60:02d}:{sec%60:02d}'
def event_label(status):
    return {'prototype near miss':'Near miss detected','overlap / review':'Overlap detected — review','unresolved / track lost':'Unresolved — track lost','unresolved / clip ended':'Unresolved — clip ended'}.get(status,status)
def event_row(e):
    a,b=(list(e['classes'])+['—','—'])[:2]
    st.markdown(f'<div class="event-row">{badge(e["severity"])}<div><div class="event-pair">{esc(str(a).title())} ↔ {esc(str(b).title())}</div>'
        f'<div class="event-meta">{esc(event_label(e["status"]))}</div></div><div class="event-time">{fmt_time(e["timestamp"])}</div>'
        f'<div class="event-risk" style="color:{COLORS.get(e["severity"],"var(--text)")}">Risk {e["peak_risk"]}</div></div>',unsafe_allow_html=True)

def session():
    out=Path(st.session_state.get('analysis_dir',ROOT/'outputs/demo'))
    p=out/'analytics.json'
    return (json.loads(p.read_text()),out) if p.exists() else (None,out)
def video_metrics(s):
    cols=st.columns(5)
    for c,(label,val,sub) in zip(cols,[('Road users tracked',s['road_users'],'Temporary IDs; fragmentation possible'),('Near misses',s['near_misses'],'Prototype candidates'),('High-risk episodes',s['high_interactions'],'Deduplicated pair interactions'),('Peak interaction',s['peak_risk'],'Highest pair score / 100'),('Live clip index',s['live_risk'],'90th percentile frame risk / 100')]):
        with c: card(label,val,sub,COLORS.get(category(float(val))) if 'index' in label or 'Peak' in label else 'var(--text)')
def render_video(s,out,label='LIVE ANALYSIS'):
    st.markdown(f'<div class="video-shell"><div class="video-topbar"><span>{esc(label)}</span><span style="color:var(--risk-low)">● AI ACTIVE</span></div>',unsafe_allow_html=True)
    st.video(str(out/'processed.mp4'))
    st.markdown('</div>',unsafe_allow_html=True)
    stat_row([(f"{s['duration']}s",'analyzed'),(s['frames_analyzed'],'frames'),(f"{s['throughput_fps']} fps",s['device'].upper()),('2.5s','path projection')])
def active_conflict_card(s):
    crit=[e for e in s.get('events',[]) if e['severity']=='CRITICAL']
    if not crit: return
    top=max(crit,key=lambda e:e['peak_risk']); a,b=(list(top['classes'])+['—','—'])[:2]
    st.markdown(f'''<div class="conflict-card">{badge('CRITICAL')}
        <div style="font-size:20px;font-weight:700;margin:10px 0 12px">{esc(str(a).title())} ↔ {esc(str(b).title())}</div>
        <div style="display:flex;gap:36px">
        <div><div class="label" style="color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:.1em">Time to Conflict {tip('Estimated time before two projected road-user paths reach their closest conflict point.')}</div><div style="font-size:24px;font-weight:750">{top['min_ttc']:.1f} sec</div></div>
        <div><div class="label" style="color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:.1em">Risk</div><div style="font-size:24px;font-weight:750">{top['peak_risk']} / 100</div></div>
        </div></div>''',unsafe_allow_html=True)
def maybe_toast(s,out):
    if HOSTED or st.session_state.get('analysis_kind')!='Fresh local analysis': return
    flag=f'toast_{out}'
    if st.session_state.get(flag): return
    st.session_state[flag]=True
    nm=[e for e in s.get('events',[]) if e['status']=='prototype near miss']
    if nm:
        top=max(nm,key=lambda e:e['peak_risk']); a,b=(list(top['classes'])+['—','—'])[:2]
        st.toast(f"Near miss detected — {str(a).title()} ↔ {str(b).title()} · peak risk {top['peak_risk']}",icon='⚠️')

def geo_plot(d,color='score',size='crashes',title='Spatial concentration'):
    if d.empty: empty_state('No data for this view','No geocoded records match these filters.'); return
    fig=px.scatter(d,x='longitude',y='latitude',color=color,size=size,size_max=24,hover_data=[c for c in ['crashes','injuries','score','borough'] if c in d],color_continuous_scale=['#67e8b5','#f6cf6b','#ff985b','#ff5d78'],range_color=[0,100],title=title)
    if title=='Predicted injury context': fig.update_traces(marker_symbol='diamond')
    fig.update_yaxes(scaleanchor='x',scaleratio=1.32)
    chart(fig,480)
    st.caption('Offline geographic view · WGS84 longitude / latitude · scroll to zoom, drag to inspect. No online map tiles required.')
def flow_ribbon():
    steps=[('01','Past','Historical accidents'),('02','Present','Live traffic + near misses'),('03','Future','Risk prediction'),('◉','CrashZero','Dynamic safety intelligence')]
    parts=[]
    for i,(n,label,desc) in enumerate(steps):
        if i: parts.append('<div class="flow-arrow">→</div>')
        parts.append(f'<div class="flow-step"><div class="flow-num">{esc(n)}</div><div class="flow-title">{esc(label)}</div><div class="flow-sub">{esc(desc)}</div></div>')
    st.markdown('<div class="flow">'+''.join(parts)+'</div>',unsafe_allow_html=True)

ICONS={'Overview':'◎','Live Analysis':'▶','City Risk':'⬢','Future Risk':'◈','History':'▤','Near Misses':'△','Conflict Zones':'◍','About':'ⓘ'}
with st.sidebar:
    st.markdown('''<div class="brand-row"><svg class="brand-mark" width="26" height="26" viewBox="0 0 26 26" xmlns="http://www.w3.org/2000/svg">
        <path d="M3 20 C 9 20, 10 13, 13 13" stroke="#9aa4b2" stroke-width="2" fill="none" stroke-linecap="round"/>
        <path d="M23 20 C 17 20, 16 13, 13 13" stroke="#67e8b5" stroke-width="2" fill="none" stroke-linecap="round"/>
        <circle cx="13" cy="13" r="2.2" fill="#67e8b5"/></svg>
        <span class="brand">CRASH<span>ZERO</span></span></div><div class="tagline">Predict Risk Before Impact</div><div class="hr"></div>''',unsafe_allow_html=True)
    page=st.radio('INTELLIGENCE WORKSPACE',list(ICONS.keys()),format_func=lambda p:f'{ICONS[p]}   {p}',label_visibility='collapsed')
    st.markdown('<div class="hr"></div><div class="eyebrow">SYSTEM STATUS</div>'
        f'<div class="status-line"><span class="dot"></span>{"Cached cloud demo" if HOSTED else "AI engine active"}</div>'
        f'<div class="status-line" style="margin-bottom:12px"><span class="dot" style="background:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)"></span>{"Read-only hosted preview" if HOSTED else "Demo ready"}</div>',unsafe_allow_html=True)
    st.caption('YOLO11n · ByteTrack — anonymous road-user tracking. No face or plate recognition.')
    st.caption('Research prototype · v1.0')
    saved=sorted((ROOT/'outputs/sessions').glob('*/analytics.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    if saved:
        with st.expander('Saved video sessions'):
            selected=st.selectbox('Session',saved,format_func=lambda p: p.parent.name)
            if st.button('Restore session'):
                st.session_state.analysis_dir=str(selected.parent); st.session_state.analysis_kind='Saved local analysis'; st.rerun()

s,out=session(); df=history()
if df.empty and page in ['City Risk','History','Future Risk']:
    st.warning('Historical dataset unavailable. Run scripts/fetch_data.py online once. Video intelligence remains available.'); st.stop()

if page=='Overview':
    st.markdown('<div class="hero"><div class="eyebrow">ROAD SAFETY INTELLIGENCE / COMMAND CENTER</div><h1>See the risk. Before the impact.</h1><p class="lead">AI-powered road-safety intelligence that combines historical accident patterns, live traffic conflicts and predictive risk analysis.</p><div class="quote">“We don’t want a crash to be the first data point telling us that an intersection is dangerous.”</div></div>',unsafe_allow_html=True)
    flow_ribbon()
    scope=st.segmented_control('Evidence scope',['Active camera','NYC historical context'],default='Active camera')
    if scope=='Active camera':
        live=s['live_risk'] if s else None; fused=fuse(live=live)
        vals=[('Dynamic risk',fused['score'],'Available-source index · live only'),('Historical risk','—','Camera location is unverified'),('Predicted risk','—','No matched historical model'),('Live risk',live,'Clip index · 90th percentile')]
    else:
        borough=st.selectbox('NYC borough',sorted(df[df.borough!='UNKNOWN'].borough.unique()))
        model,metrics=predictor(); tl=timeline(model,borough,0,'SEDAN'); hist=historical_index(df,borough); pred=float(tl.score.mean()); fused=fuse(historical=hist,predictive=pred)
        vals=[('Dynamic risk',fused['score'],'Historical + conditional injury index'),('Historical risk',hist,'Relative reported crash count / borough'),('Predicted risk',round(pred,1),'Mean modeled injury likelihood × 100'),('Live risk','—','No verified CCTV at this location')]
    cols=st.columns([1.3,1,1,1])
    for i,(c,(label,val,sub)) in enumerate(zip(cols,vals)):
        with c:
            color=COLORS.get(category(val),'var(--text)') if isinstance(val,(int,float)) else 'var(--text-muted)'
            card(label,'—' if val is None else val,sub,color,primary=(i==0),score=val if isinstance(val,(int,float)) else None)
    left,right=st.columns([1.65,1])
    with left:
        section('Live vision / active camera')
        if s:
            st.image(str(out/'preview.jpg'),width='stretch')
            st.caption('REAL VIDEO · Cached algorithm output · Camera location unverified · No confirmed collision claim')
        else: st.info('Open Live Analysis to analyze a video.')
    with right:
        section('Evidence behind the score',tip_text='Missing sources are excluded and remaining weights are normalized.')
        if scope=='Active camera' and s:
            items=[(s['high_interactions'],'high-risk interactions'),(s['near_misses'],'near-miss candidates'),(f"{s['peak_risk']}/100",'peak risk'),(f"{s['current_risk']}/100",'last frame')]
            if s['conflict_types']:
                top=max(s['conflict_types'],key=s['conflict_types'].get); items.insert(2,(top,'most frequent'))
            stat_row(items)
            st.caption(emerging_status(s)['reason'])
        else:
            st.caption('Combines reported crash volume and modeled injury severity context — not a probability of a crash occurring. Scenario: Monday, sedan, mean of 24 hourly estimates.')
        weight_bar(fused['weights'])
    if s:
        cols=st.columns(4)
        for c,(l,v,sub) in zip(cols,[('Near misses',s['near_misses'],'Prototype candidates'),('Critical interactions',s['critical_interactions'],'Peak score ≥81'),('Road users tracked',s['road_users'],'Temporary anonymous IDs'),('Historical peak hour',f'{int(df.hour.value_counts().idxmax()):02d}:00' if not df.empty else '—','NYC 2024 · crash count, not exposure')]):
            with c: card(l,v,sub)
        if s.get('events'):
            section('Recent safety events','Most recent high-risk interactions detected in the analyzed clip.')
            for e in sorted(s['events'],key=lambda e:e['timestamp'],reverse=True)[:4]: event_row(e)
    if scope=='NYC historical context':
        boroughs=sorted(df[df.borough!='UNKNOWN'].borough.unique())
        ranked=sorted(((b,historical_index(df,b)) for b in boroughs),key=lambda x:-(x[1] or 0))[:3]
        if ranked:
            section('Attention required','Highest historical concentration by borough · open City Risk for the full spatial view.')
            for b,score in ranked:
                cat=category(score)
                st.markdown(f'<div class="event-row">{badge(cat)}<div><div class="event-pair">{esc(b.title())}</div><div class="event-meta">Historical concentration index</div></div>'
                    f'<div class="event-risk" style="margin-left:auto;color:{COLORS.get(cat)}">{score}</div></div>',unsafe_allow_html=True)

elif page=='Live Analysis':
    page_header('Live Analysis','Analyze road-user movement and detect developing traffic conflicts.')
    st.caption('Processing runs on this Mac; playback uses the completed analysis.' if not HOSTED else 'Hosted demonstration: cached local analysis. Uploads and inference are available in the local version.')
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
    with a: duration=st.slider('Maximum seconds to analyze',5,120,35,5,help='More seconds gives more evidence but takes longer to process.')
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
        except Exception as e: st.error(f"Analysis couldn't be completed: {e}")
    if st.button('Load offline demo analytics'):
        st.session_state.analysis_dir=str(ROOT/'outputs/demo'); st.session_state.analysis_kind='Cached demo analysis'; st.rerun()
    s,out=session()
    if s:
        maybe_toast(s,out)
        st.markdown(f"**{st.session_state.get('analysis_kind','Cached demo analysis')}** · {s['evidence']}")
        video_metrics(s)
        active_conflict_card(s)
        l,r=st.columns([2,1])
        with l: render_video(s,out)
        with r:
            section('What the engine observed')
            stat_row([(s['critical_interactions'],'critical interactions'),(f"{s['current_risk']}/100",'last frame'),(f"{s['duration']}s",'analyzed'),(f"{s['analysis_fps']} fps",'sampling')])
            st.caption(s['risk_definition'])
            st.download_button('Download processed video',(out/'processed.mp4').read_bytes(),'crashzero_processed.mp4','video/mp4')
            st.download_button('Export analytics JSON',(out/'analytics.json').read_bytes(),'crashzero_analytics.json','application/json')
            st.download_button('Export tracks CSV',(out/'tracks.csv').read_bytes(),'crashzero_tracks.csv','text/csv')
        section('Risk evolution','Pair risk across the analyzed clip · dotted lines mark moderate / high / critical thresholds.')
        fig=px.area(pd.DataFrame(s['timeline']),x='timestamp',y='risk',labels={'timestamp':'Video time (seconds)','risk':'Pair risk / 100'},color_discrete_sequence=['#67e8b5'])
        chart(threshold_lines(fig))
        if s['truncated']: st.info('Analysis stopped at the selected duration limit. The remainder was not analyzed.')

elif page=='History':
    page_header('Accident History','Understand where, when and under what conditions previous accidents occurred.')
    evidence()
    a,b,c=st.columns(3)
    with a: borough=st.selectbox('Borough',['All']+sorted(df.borough.unique()))
    with b: dates=st.date_input('Date range',(df.date.min().date(),df.date.max().date()),min_value=df.date.min().date(),max_value=df.date.max().date())
    with c: vehicle=st.selectbox('Primary vehicle',['All']+sorted(df.vehicle.unique()))
    d=df.copy()
    if borough!='All': d=d[d.borough==borough]
    if vehicle!='All': d=d[d.vehicle==vehicle]
    if len(dates)==2: d=d[d.date.between(pd.Timestamp(dates[0]),pd.Timestamp(dates[1]))]
    if d.empty: empty_state('No matching crashes','No crashes match these filters. Widen the borough, vehicle or date range.'); st.stop()
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

elif page=='Future Risk':
    page_header('Future Risk','Understand where and when road-safety conditions may become elevated.')
    evidence()
    st.info('This model estimates injury likelihood GIVEN a reported crash. It cannot estimate whether a crash will happen. The timeline applies historical relationships to a selected future context.')
    model,metrics=predictor()
    a,b,c=st.columns(3)
    with a: borough=st.selectbox('Location / borough',sorted(df[df.borough!='UNKNOWN'].borough.unique()))
    with b: date=st.date_input('Scenario date',datetime.date.today()+datetime.timedelta(days=1),key='future_date')
    with c: vehicle=st.selectbox('Vehicle context',sorted(df.vehicle.unique()),index=list(sorted(df.vehicle.unique())).index('SEDAN'))
    tl=timeline(model,borough,date.weekday(),vehicle)
    peak=tl.loc[tl.score.idxmax()]; average=float(tl.score.mean()); hist=historical_index(df,borough)
    a,b,c=st.columns(3)
    with a: card('Predicted risk',f'{peak.score:.1f}/100',f"Highest-risk window · {int(peak.hour):02d}:00–{int(peak.hour)+1:02d}:00",COLORS[peak.category],primary=True,score=peak.score)
    with b: card('Daily mean index',f'{average:.1f}/100','Mean of 24 modeled hourly contexts')
    with c: card('Temporal holdout AUC',metrics['roc_auc'],'Oct–Dec 2024 · injury classification')
    section('Risk timeline','Modeled injury-context estimate across the 24-hour scenario.')
    fig=px.line(tl,x='hour',y='score',markers=True,labels={'hour':'Hour in selected local context','score':'Conditional injury estimate × 100'})
    chart(threshold_lines(fig),330)
    blocks=tl.groupby(tl.hour//2).agg(score=('score','mean')).reset_index()
    blocks['Window']=blocks.hour.map(lambda h:f'{h*2:02d}:00–{h*2+2:02d}:00');blocks['Category']=blocks.score.map(category)
    st.dataframe(blocks[['Window','score','Category']].rename(columns={'score':'Injury index / 100'}),hide_index=True,width='stretch')
    l,r=st.columns(2)
    with l:
        section('Evidence and explanation',tip_text='The classifier uses borough, hour, weekday and vehicle context only. These associations do not establish causation.')
        subset=df[(df.borough==borough)&(df.weekday==date.weekday())&(df.vehicle==vehicle)]
        stat_row([(borough.title(),'borough'),(date.strftime('%A'),'weekday'),(vehicle.title(),'vehicle')])
        if len(subset): stat_row([(f'{len(subset):,}','matching records'),(f'{subset.injury.mean():.1%}','observed injury share')])
        else: st.caption('No exact matching historical records; this context has weak support.')
        st.json(metrics,expanded=False)
    with r:
        section('Transparent dynamic fusion',tip_text='Composite safety-priority index; component meanings differ. Not a calibrated probability. No location-matched live source is available.')
        wh=st.slider('Historical weight',0,100,25,help='Share of the dynamic index from reported crash concentration.')
        wp=st.slider('Predictive weight',0,100,30,help='Share of the dynamic index from the modeled injury-context estimate.')
        f=fuse(hist,average,None,{'historical':wh,'predictive':wp,'live':0})
        card('Dynamic context index',f['score'] if f['score'] is not None else '—','Weights normalized across available sources',score=f['score'])
        st.json(f,expanded=False)
    st.download_button('Export hourly predictions',tl.to_csv(index=False).encode(),'crashzero_predictions.csv','text/csv')

elif page=='City Risk':
    page_header('City Risk','See where road-safety risk is concentrated and where new hotspots may be emerging.')
    evidence()
    a,b,c=st.columns(3)
    with a: layer=st.selectbox('Evidence layer',['Historical density','Historical severity','Predicted injury context','Emerging hotspots'])
    with b: hours=st.slider('Hour range',0,23,(0,23),help='Filter crashes by hour of day.')
    with c: severity=st.multiselect('Severity',sorted(df.severity.unique()),default=sorted(df.severity.unique()))
    a,b=st.columns(2)
    with a: dates=st.date_input('Map date range',(df.date.min().date(),df.date.max().date()),key='map_date')
    with b: vehicle=st.selectbox('Map vehicle',['All']+sorted(df.vehicle.unique()))
    d=df[df.hour.between(*hours)&df.severity.isin(severity)].copy()
    if len(dates)==2:d=d[d.date.between(pd.Timestamp(dates[0]),pd.Timestamp(dates[1]))]
    if vehicle!='All':d=d[d.vehicle==vehicle]
    st.markdown(''.join(f'<span class="badge {c}"><span class="dot"></span>{c} {r}</span>&nbsp;' for c,r in [('LOW','0–30'),('MODERATE','31–60'),('HIGH','61–80'),('CRITICAL','81–100')]),unsafe_allow_html=True)
    st.write('')
    if layer=='Emerging hotspots':
        empty_state('No emerging hotspots to show','No verified geographic link exists between the demo camera and NYC crash history. Open Conflict Zones for measured image-space conflict zones.')
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
        if not grid.empty:
            section('Attention required','Highest-scoring locations in the current filter.')
            for _,row in grid.sort_values('score',ascending=False).head(3).iterrows():
                cat=category(row.score)
                loc=row.borough.title() if 'borough' in row else f"{row.latitude:.3f}, {row.longitude:.3f}"
                st.markdown(f'<div class="event-row">{badge(cat)}<div><div class="event-pair">{esc(loc)}</div><div class="event-meta">{int(row.crashes)} crashes in filter</div></div>'
                    f'<div class="event-risk" style="margin-left:auto;color:{COLORS.get(cat)}">{row.score:.1f}</div></div>',unsafe_allow_html=True)
        if st.toggle('Show online street basemap (requires internet)') and not grid.empty:
            import pydeck as pdk
            grid['color']=grid.score.map(lambda x:[int(COLORS[category(x)].lstrip('#')[i:i+2],16) for i in (0,2,4)])
            deck=pdk.Deck(layers=[pdk.Layer('ScatterplotLayer',grid,get_position='[longitude,latitude]',get_fill_color='color',get_radius=240,pickable=True)],initial_view_state=pdk.ViewState(latitude=40.73,longitude=-73.95,zoom=10),map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',tooltip={'text':'Score: {score}\nCrashes: {crashes}'})
            st.pydeck_chart(deck)
        st.dataframe(grid.sort_values('score',ascending=False).head(20),hide_index=True,width='stretch')

elif page in ['Near Misses','Conflict Zones']:
    if page=='Near Misses': page_header('Near Misses','High-risk interactions where road users narrowly avoided conflict.')
    else: page_header('Conflict Zones','Areas where dangerous interactions repeatedly occur.')
    if not s: empty_state('No analysis yet','Analyze a video in Live Analysis first.'); st.stop()
    st.caption(f"Session {s['session_id']} · Stored analysis · Anonymous temporary IDs")
    if page=='Near Misses':
        video_metrics(s)
        status=st.selectbox('Event status',['All','prototype near miss','overlap / review','unresolved / track lost','unresolved / clip ended'])
        events=pd.DataFrame(s['events'])
        if not events.empty:
            if status!='All':events=events[events.status==status]
        if not events.empty:
            section('Event log')
            for _,row in events.sort_values('peak_risk',ascending=False).head(6).iterrows(): event_row(row.to_dict())
            st.dataframe(events,hide_index=True,width='stretch')
        else: empty_state('No near misses yet','No high-risk episodes met the threshold in this clip. No events have been fabricated.')
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
            section(emerging['status'],tip_text='A location showing increasing conflict or near-miss activity even if recorded crash history is limited.')
            st.caption(emerging['reason'])
            stat_row([('Increasing' if emerging['increasing'] else 'Not increasing','risk trend'),(f"{emerging['early_rate']:.2f}",'early rate/frame'),(f"{emerging['late_rate']:.2f}",'late rate/frame')])
            card('Distinct conflict episodes',s['high_interactions'],'Counts include unresolved and overlap/review episodes')
            if s['events']:
                zones={}
                for e in s['events']:
                    if 0<=e['x']<s['width'] and 0<=e['y']<s['height']:
                        key=(min(2,int(e['x']/s['width']*3)),min(2,int(e['y']/s['height']*3)));zones[key]=zones.get(key,0)+1
                if zones:
                    z=max(zones,key=zones.get)
                    stat_row([(f"{['top','middle','bottom'][z[1]]} {['left','center','right'][z[0]]}",'most repeated zone'),(zones[z],'episodes there')])
        if s['conflict_types']:
            types=pd.DataFrame(s['conflict_types'].items(),columns=['Interaction','Episodes']); types['Share']=types.Episodes/types.Episodes.sum()*100
            section('High-risk interaction types'); chart(px.bar(types,x='Interaction',y='Episodes',text=types.Share.map(lambda x:f'{x:.0f}%')))
        st.download_button('Export heatmap',(out/'heatmap.jpg').read_bytes(),'crashzero_heatmap.jpg','image/jpeg')

elif page=='About':
    page_header('Before a crash becomes a data point.','CrashZero combines historical analysis, computer vision and transparent risk indicators to support earlier investigation of road-safety concerns.')
    for c,(title,body) in zip(st.columns(3),[('PAST','NYC police-reported collisions → cleaning → hourly patterns → spatial concentration.'),('PRESENT','YOLO11n → ByteTrack → image-space motion → 2.5-second closest approach → episode review.'),('FUTURE','Random forest → conditional injury context → hourly scenario timeline → available-source fusion.')]):
        with c: st.markdown(f'<div class="card"><div class="label">{title}</div><div class="sub" style="font-size:13px;color:var(--text-secondary);margin-top:8px">{body}</div></div>',unsafe_allow_html=True)
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
