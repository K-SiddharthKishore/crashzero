from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from config.settings import ROOT
from src.analysis_context import camera_selection, file_selection


def open_hotspot():
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    next(b for b in app.button if b.label == 'Open Hotspot Detector').click().run()
    return app


@pytest.mark.parametrize('source', ['Upload Video', 'Live Camera'])
def test_module_one_source_tabs(source):
    app = open_hotspot()
    app.segmented_control(key='m1_source_tab').set_value(source).run()
    assert app.segmented_control(key='m1_source_tab').value == source
    assert not app.exception


def test_live_camera_can_open_risk_areas_without_stopping():
    app = open_hotspot()
    app.segmented_control(key='m1_source_tab').set_value('Live Camera').run()
    next(s for s in app.selectbox if s.label == 'Camera source').set_value('Device webcam').run()
    selection = camera_selection('CAM-01', 'webcam', 0)
    fake = SimpleNamespace(source=SimpleNamespace(live=True), source_id=selection['id'],
        source_kind='live camera', analysis_id='live-test', thread=SimpleNamespace(is_alive=lambda: True),
        camera=SimpleNamespace(name='Local camera', camera_id='CAM-01'), calibration=None, out=ROOT/'outputs',
        get=lambda: {'status':'MONITORING','events':[],'frame':None,'risk':0,'road_users':0,
                     'conflicts':0,'near_misses':0,'fps':5.,'timestamp':1.})
    app.session_state['worker'] = fake
    app.run()
    next(b for b in app.button if b.label == 'View Key Risk Areas →').click().run()
    assert app.toggle(key='cz_risk_open').value is True
    assert fake.thread.is_alive()
    assert not app.exception


def test_navigation_has_only_two_modules_and_settings():
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert list(app.segmented_control(key='cz_primary_nav').options) == [
        'Accident Hotspot Detector', 'Accident Detector & Emergency Caller', 'Settings']
    next(b for b in app.button if b.label == 'Open Hotspot Detector').click().run()
    assert app.segmented_control(key='m1_source_tab').value == 'Upload Video'
    app.segmented_control(key='cz_primary_nav').set_value('Accident Detector & Emergency Caller').run()
    assert any(t.value == 'Accident Detection' for t in app.title)
    app.segmented_control(key='cz_primary_nav').set_value('Settings').run()
    assert any(t.value == 'Settings' for t in app.title)
    assert not app.exception


def test_accident_result_survives_settings_navigation_without_new_analysis():
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    next(b for b in app.button if b.label == 'Open Accident Detector').click().run()
    video = ROOT / 'data/simulations/normal.mp4'
    app.session_state['test_saved_uploads'] = [(str(video), 'normal.mp4')]
    fake = SimpleNamespace(snapshot=lambda: ([], True, False))
    app.session_state['test_upload_worker'] = fake
    app.run()
    app.segmented_control(key='cz_primary_nav').set_value('Settings').run()
    app.segmented_control(key='cz_primary_nav').set_value('Accident Detector & Emergency Caller').run()
    assert app.session_state['test_upload_worker'] is fake
    assert app.session_state['test_saved_uploads'][0][0] == str(video)
    assert not app.exception


@pytest.mark.parametrize('state,expanded', [('COMPLETED',True),('STOPPED',False),('ERROR',False)])
def test_file_completion_reveals_risk_areas_only_on_success(state, expanded):
    app = open_hotspot()
    app.toggle(key='m1_demo_recording').set_value(True).run()
    next(s for s in app.selectbox if s.label == 'Offline scenario').set_value('Highway').run()
    path = ROOT / 'data/demo/highway.mp4'
    selection = file_selection(path, 'Highway')
    app.session_state['selected_source'] = selection
    fake = SimpleNamespace(source=SimpleNamespace(live=False), source_id=selection['id'],
        source_kind='video', analysis_id='test-analysis-'+state,
        thread=SimpleNamespace(is_alive=lambda:False),
        camera=SimpleNamespace(camera_id='DEMO',name='Demo camera'), calibration=None, out=path,
        get=lambda:{'status':state,'events':[],'frame':None,'heatmap':None,'risk':0,
                    'road_users':0,'conflicts':0,'near_misses':0,'fps':0.,'timestamp':0.,
                    'message':'Analysis failed' if state=='ERROR' else None})
    app.session_state['worker'] = fake
    app.run()
    assert app.toggle(key='cz_risk_open').value is expanded
    assert not app.exception
