from streamlit.testing.v1 import AppTest
from config.settings import ROOT


def test_hosted_v2_sources_and_session_isolation(monkeypatch):
    monkeypatch.setenv('CRASHZERO_V2_HOSTED','1')
    first=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    second=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    assert not first.exception and not second.exception
    assert 'LIVE CAMERA' not in first.segmented_control[0].options
    assert list(first.selectbox[0].options)==['cpu']
    assert first.session_state['cloud_session_id']!=second.session_state['cloud_session_id']
    for page in ['Conflict Zones','Incidents']:
        first.radio[0].set_value(page).run()
        assert not first.exception
