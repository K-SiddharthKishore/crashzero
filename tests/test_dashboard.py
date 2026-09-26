from streamlit.testing.v1 import AppTest
import pytest
from config.settings import ROOT

@pytest.mark.parametrize('page',['Live Analysis','Conflict Zones','Incidents'])
def test_v2_pages(page):
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    app.radio[0].set_value(page).run()
    assert not app.exception
    assert list(app.radio[0].options)==['Live Analysis','Conflict Zones','Incidents']

def test_default_is_live():
    app=AppTest.from_file(str(ROOT/'app.py')).run()
    assert app.radio[0].value=='Live Analysis'
    assert not app.exception
