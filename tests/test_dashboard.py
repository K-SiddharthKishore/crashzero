from streamlit.testing.v1 import AppTest
import pytest
from config.settings import ROOT
@pytest.fixture(scope='module')
def app(): return AppTest.from_file(str(ROOT/'app.py'),default_timeout=40).run()
@pytest.mark.parametrize('page',['Overview','City Risk','History','Future Risk','Live Analysis','Near Misses','Conflict Zones','About'])
def test_page(app,page):
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception

def test_city_layers_and_empty_filter(app):
    app.sidebar.radio[0].set_value('City Risk').run()
    for layer in ['Historical severity','Predicted injury context','Emerging hotspots']:
        app.main.selectbox[0].set_value(layer).run();assert not app.exception
    app.main.selectbox[0].set_value('Historical density').run()
    app.multiselect[0].set_value([]).run();assert not app.exception

def test_overview_historical_scope(app):
    app.sidebar.radio[0].set_value('Overview').run()
    app.segmented_control[0].set_value('NYC historical context').run()
    assert not app.exception
