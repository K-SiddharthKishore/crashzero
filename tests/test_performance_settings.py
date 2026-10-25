"""Guard against work that blocks every high-frequency dashboard refresh."""
import tomllib
from config.settings import ROOT
from streamlit.testing.v1 import AppTest


def test_monitor_does_not_force_full_heap_collection():
    config = tomllib.loads((ROOT/'.streamlit/config.toml').read_text())
    assert config['runner']['postScriptGC'] is False


def test_file_analysis_defaults_to_fast_unpaced_mode():
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()
    next(b for b in app.button if b.label=='Open Hotspot Detector').click().run()
    assert not app.exception
    assert next(r for r in app.radio if r.label == 'Analysis quality').value == 'Fast'
    assert not next(c for c in app.checkbox if c.label == 'Play at normal speed').value
