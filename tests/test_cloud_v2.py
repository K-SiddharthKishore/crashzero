from streamlit.testing.v1 import AppTest

from config.settings import ROOT
from test_lab.config import TestLabConfig as LabConfig


def _open_hotspot(app):
    next(b for b in app.button if b.label == 'Open Hotspot Detector').click().run()
    return app


def test_hosted_v2_sources_and_session_isolation(monkeypatch):
    monkeypatch.setenv('CRASHZERO_V2_HOSTED', '1')
    first = _open_hotspot(AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run())
    second = _open_hotspot(AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run())
    assert not first.exception and not second.exception
    assert 'Live Camera' in first.segmented_control(key='m1_source_tab').options
    assert next(s for s in first.selectbox if s.label == 'Inference device').options == ['cpu']
    assert first.session_state['cloud_session_id'] != second.session_state['cloud_session_id']
    first.toggle(key='cz_risk_open').set_value(True).run()
    first.toggle(key='cz_incidents_open').set_value(True).run()
    assert not first.exception


def test_cloud_camera_selection_validation_and_incident_scope(monkeypatch):
    monkeypatch.setenv('CRASHZERO_V2_HOSTED', '1')
    app = _open_hotspot(AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run())
    app.segmented_control(key='m1_source_tab').set_value('Live Camera').run()
    assert not app.exception
    assert next(s for s in app.selectbox if s.label == 'Camera source').options == ['IP / CCTV stream']
    field = app.text_input(key='_camera_stream_url')
    field.set_value('rtsp://192.168.1.20/live').run()
    assert app.session_state['selected_source'] is None
    assert next(b for b in app.button if b.label == 'Start analysis').disabled
    app.text_input(key='_camera_stream_url').set_value('rtsp://operator:secret@8.8.8.8/live').run()
    selected = app.session_state['selected_source']
    assert 'secret' not in str(selected) and '8.8.8.8' not in str(selected)
    assert not next(b for b in app.button if b.label == 'Start analysis').disabled
    app.toggle(key='cz_incidents_open').set_value(True).run()
    app.toggle(key='cz_incidents_open').set_value(False).run()
    assert app.session_state['selected_source'] == selected
    app.text_input(key='_camera_stream_url').set_value('rtsp://8.8.4.4/live').run()
    assert app.session_state['selected_source']['id'] != selected['id']
    assert not app.exception


def test_hosted_module_two_uses_session_storage(monkeypatch):
    monkeypatch.setenv('CRASHZERO_V2_HOSTED', '1')
    apps = [AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run() for _ in range(2)]
    for app in apps:
        next(b for b in app.button if b.label == 'Open Accident Detector').click().run()
        assert not app.exception
    assert apps[0].session_state['cloud_session_id'] != apps[1].session_state['cloud_session_id']
    for app in apps:
        data_dir = ROOT/'outputs/sessions/cloud'/app.session_state['cloud_session_id']/'test_lab'
        assert LabConfig.load(data_dir=data_dir).db_path.exists()
