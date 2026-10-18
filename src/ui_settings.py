"""Optional camera configuration and local developer test-call controls."""
import json
import os
from pathlib import Path
import streamlit as st
from src.calibration import RoadCalibration
from src.alerts.config import CallConfig
from src.alerts.service import AlertService, configuration_key


@st.fragment(run_every=2.)
def call_settings(storage_root, hosted):
    st.markdown('**TEST MODE · telephone notifications**')
    config=CallConfig.load()
    service=AlertService(storage_root/'incidents/calls' if hosted else None)
    st.caption(f'Provider: {config.provider} · destination: {config.masked_destination}')
    st.caption('Real calls are disabled in public deployments and automated tests.')
    if config.reason: st.warning(config.reason)
    auto=st.checkbox('AUTO TEST CALL',value=config.auto,disabled=hosted,key='auto_test_calls')
    if not hosted: os.environ['AUTO_TEST_CALL_ENABLED']='true' if auto else 'false'
    if st.button('SEND TEST CALL',disabled=not config.allowed):
        st.session_state.call_future=service.manual()
    future=st.session_state.get('call_future')
    if future:
        if future.done(): st.write(future.result())
        else: st.info('CALLING… awaiting provider status.')
    attempts=service.store.list()
    if attempts:
        st.dataframe([{'attempt':r['id'],'provider':r['provider'],'kind':r['kind'],'status':r['status']} for r in attempts[:10]],hide_index=True)
        completed=[r for r in attempts if r['kind']=='manual' and r['status']=='COMPLETED' and r['provider']==config.provider and r['destination']==config.destination]
        if completed and not hosted and st.button('I heard the test message on my permitted test phone'):
            service.store.acknowledge(configuration_key(config),completed[0]['id'])
            st.success('Manual test acknowledged for this provider and destination.')
        if not hosted:
            with st.expander('Developer: authorize another real call for a recorded event'):
                st.caption('Detection and mock incidents work on every replay. This reset only releases a selected real-call reservation; the eligibility and kill-switch checks still apply.')
                real=[r for r in attempts if r['provider']!='mock' and r['kind']=='automatic']
                if real:
                    selected=st.selectbox('Call reservation',[r['id'] for r in real])
                    confirmation=st.text_input('Type AUTHORIZE ANOTHER REAL TEST CALL')
                    if st.button('Reset selected reservation',disabled=confirmation!='AUTHORIZE ANOTHER REAL TEST CALL'):
                        service.store.reset(selected,confirmation);st.success('Authorization recorded.')
                else: st.caption('No real automatic reservations.')


def calibration_settings(camera_id, storage_root, hosted):
    with st.expander('Optional road calibration & movement corridors'):
        st.caption('Coordinates refer to the analysis image (maximum width 960 px). Four ordered convex image points map to a normalized road plane, not km/h or meters.')
        enabled=st.checkbox('Use camera road configuration',key='calibration_enabled_'+camera_id)
        if not enabled: return None
        path=Path(storage_root)/'sessions'/'camera-config.json'
        configs={}
        if path.exists():
            try: configs=json.loads(path.read_text())
            except (OSError,ValueError): pass
        value=st.text_area('Road configuration JSON',value=json.dumps(configs.get(camera_id,{
            'image_points':[], 'road_points':[], 'corridors':[]}),indent=2),key='calibration_json_'+camera_id,
            help='image_points and road_points each contain four [x,y] pairs. corridors contain movement (STRAIGHT, LEFT TURN, RIGHT TURN, MERGE) and polygon vertices in image pixels.')
        try:
            config=json.loads(value); calibration=RoadCalibration(config)
        except (ValueError,TypeError,KeyError) as exc:
            st.warning('Invalid road configuration; using image-space fallback. '+str(exc));return None
        st.caption('Coordinates: '+calibration.units)
        worker=st.session_state.get('worker')
        if worker and worker.get().get('frame') is not None:
            import cv2
            import numpy as np
            preview=worker.get()['frame'].copy()
            for region in config.get('corridors',[]):
                cv2.polylines(preview,[np.asarray(region['polygon'],dtype=np.int32)],True,(255,200,50),2)
            for point in config.get('image_points',[]): cv2.circle(preview,tuple(map(int,point)),6,(80,230,150),-1)
            st.image(preview,caption='Calibration preview — applies on the next analysis')
        if st.button('Save road configuration for this camera'):
            configs[camera_id]=config;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(configs,indent=2));st.success('Saved.')
        return calibration
