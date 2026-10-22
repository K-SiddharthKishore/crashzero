from streamlit.testing.v1 import AppTest
from config.settings import ROOT
from module_2_accident_response.config import Module2Config


def test_hosted_v2_sources_and_session_isolation(monkeypatch):
    monkeypatch.setenv('CRASHZERO_V2_HOSTED','1')
    first=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    second=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    next(b for b in first.button if b.label=='Open Junction Intelligence →').click().run()
    next(b for b in second.button if b.label=='Open Junction Intelligence →').click().run()
    assert not first.exception and not second.exception
    assert 'LIVE CAMERA' in first.segmented_control[0].options
    assert list(first.selectbox[0].options)==['cpu']
    assert first.session_state['cloud_session_id']!=second.session_state['cloud_session_id']
    for page in ['Danger Spots','Incidents']:
        first.radio[0].set_value(page).run()
        assert not first.exception


def test_cloud_camera_selection_validation_and_incident_scope(monkeypatch):
    monkeypatch.setenv('CRASHZERO_V2_HOSTED','1')
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    next(b for b in app.button if b.label=='Open Junction Intelligence →').click().run()
    app.segmented_control[0].set_value('LIVE CAMERA').run()
    assert not app.exception
    assert app.selectbox[1].options == ['IP / CCTV stream']
    field=app.text_input(key='_camera_stream_url')
    field.set_value('rtsp://192.168.1.20/live').run()
    assert app.session_state['selected_source'] is None
    assert next(b for b in app.button if b.label=='Start analysis').disabled
    field=app.text_input(key='_camera_stream_url')
    field.set_value('rtsp://operator:secret@8.8.8.8/live').run()
    first=app.session_state['selected_source']
    assert 'secret' not in str(first) and '8.8.8.8' not in str(first)
    assert not next(b for b in app.button if b.label=='Start analysis').disabled
    app.radio[0].set_value('Incidents').run()
    app.radio[0].set_value('Track vehicles').run()
    assert app.session_state['selected_source'] == first
    app.text_input(key='_camera_stream_url').set_value('rtsp://8.8.4.4/live').run()
    assert app.session_state['selected_source']['id'] != first['id']
    assert not app.exception


def test_hosted_module_two_uses_session_storage(monkeypatch):
    monkeypatch.setenv('CRASHZERO_V2_HOSTED','1')
    apps=[AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run() for _ in range(2)]
    for app in apps:
        next(b for b in app.button if b.label=='Open Accident Response →').click().run()
        assert not app.exception
    assert apps[0].session_state['cloud_session_id'] != apps[1].session_state['cloud_session_id']
    for app in apps:
        data_dir=ROOT/'outputs/sessions/cloud'/app.session_state['cloud_session_id']/'module2_accident_response'
        assert Module2Config.load(data_dir=data_dir).db_path.exists()
