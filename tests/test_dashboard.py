from streamlit.testing.v1 import AppTest
import pytest
from config.settings import ROOT
from types import SimpleNamespace
from src.analysis_context import file_selection, camera_selection

@pytest.mark.parametrize('page',['Track vehicles','Danger Spots','Incidents'])
def test_module_one_pages(page):
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    next(b for b in app.button if b.label=='Open Junction Intelligence →').click().run()
    app.radio[0].set_value(page).run()
    assert not app.exception


def test_live_camera_can_open_danger_spots_without_stopping():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    next(b for b in app.button if b.label=='Open Junction Intelligence →').click().run()
    app.segmented_control[0].set_value('LIVE CAMERA').run()
    next(s for s in app.selectbox if s.label=='Camera source').set_value('Device webcam').run()
    selection=camera_selection('CAM-01','webcam',0)
    fake=SimpleNamespace(source=SimpleNamespace(live=True),source_id=selection['id'],
        source_kind='live camera',analysis_id='live-test',thread=SimpleNamespace(is_alive=lambda:True),
        camera=SimpleNamespace(name='Local camera',camera_id='CAM-01'),calibration=None,out=ROOT/'outputs',
        get=lambda:{'status':'MONITORING','events':[],'frame':None,'risk':0,'road_users':0,
            'conflicts':0,'near_misses':0,'fps':5.,'timestamp':1.})
    app.session_state['worker']=fake
    app.run()
    assert any(b.label=='View Danger Spots →' for b in app.button)
    next(b for b in app.button if b.label=='View Danger Spots →').click().run()
    assert app.radio[0].value=='Danger Spots'
    assert not app.exception
    assert list(app.radio[0].options)==['Track vehicles','Danger Spots','Incidents']

def test_module_chooser_and_switching():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    assert any(b.label=='Open Junction Intelligence →' for b in app.button)
    assert any(b.label=='Open Accident Response →' for b in app.button)
    next(b for b in app.button if b.label=='Open Junction Intelligence →').click().run()
    assert app.radio[0].value=='Track vehicles'
    assert app.segmented_control[0].value=='UPLOAD VIDEO'
    next(b for b in app.button if b.label=='← Change module').click().run()
    next(b for b in app.button if b.label=='Open Accident Response →').click().run(timeout=30)
    assert any(e.value=='Accident Response' for e in app.title)
    assert not app.exception


@pytest.mark.parametrize('state,expected', [
    ('COMPLETED','Danger Spots'),('STOPPED','Track vehicles'),('ERROR','Track vehicles')])
def test_file_completion_routes_only_on_success(state,expected):
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    next(b for b in app.button if b.label=='Open Junction Intelligence →').click().run()
    app.segmented_control[0].set_value('DEMO').run()
    path=ROOT/'data/demo/highway.mp4'
    selection=file_selection(path,'Highway')
    app.session_state['selected_source']=selection
    fake=SimpleNamespace(source=SimpleNamespace(live=False),source_id=selection['id'],
        source_kind='video',analysis_id='test-analysis-'+state,thread=SimpleNamespace(is_alive=lambda:False),
        camera=SimpleNamespace(camera_id='DEMO',name='Demo camera'),calibration=None,out=path,
        get=lambda:{'status':state,'events':[],'frame':None,'heatmap':None,'risk':0,
            'road_users':0,'conflicts':0,'near_misses':0,'fps':0.,'timestamp':0.,
            'message':'Analysis failed' if state=='ERROR' else None})
    app.session_state['worker']=fake
    app.run()
    assert app.radio[0].value==expected
    if state=='COMPLETED':
        assert any('No danger spots detected in this video' in e.value for e in app.info)
        next(b for b in app.button if b.label=='Review incident evidence →').click().run()
        assert app.radio[0].value=='Incidents'
    assert not app.exception
