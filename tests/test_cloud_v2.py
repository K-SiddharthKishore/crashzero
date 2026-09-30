from streamlit.testing.v1 import AppTest
from config.settings import ROOT


def test_hosted_v2_sources_and_session_isolation(monkeypatch):
    monkeypatch.setenv('CRASHZERO_V2_HOSTED','1')
    first=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    second=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    assert not first.exception and not second.exception
    assert 'LIVE CAMERA' in first.segmented_control[0].options
    assert list(first.selectbox[0].options)==['cpu']
    assert first.session_state['cloud_session_id']!=second.session_state['cloud_session_id']
    for page in ['Conflict Zones','Incidents']:
        first.radio[0].set_value(page).run()
        assert not first.exception


def test_cloud_camera_selection_validation_and_incident_scope(monkeypatch):
    monkeypatch.setenv('CRASHZERO_V2_HOSTED','1')
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
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
    app.radio[0].set_value('Live Analysis').run()
    assert app.session_state['selected_source'] == first
    app.text_input(key='_camera_stream_url').set_value('rtsp://8.8.4.4/live').run()
    assert app.session_state['selected_source']['id'] != first['id']
    assert not app.exception
