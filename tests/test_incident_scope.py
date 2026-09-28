import json
import sqlite3
from streamlit.testing.v1 import AppTest
from config.settings import ROOT
from src.incidents.manager import IncidentStore


def test_existing_database_migrates_without_assigning_unknown_video(tmp_path):
    legacy={'incident_id':'legacy','created_at':'2026-01-01','event_type':'LIKELY COLLISION'}
    with sqlite3.connect(tmp_path/'incidents.sqlite') as db:
        db.execute('CREATE TABLE incidents (id TEXT PRIMARY KEY,created_at TEXT,payload TEXT)')
        db.execute('INSERT INTO incidents VALUES (?,?,?)',('legacy',legacy['created_at'],json.dumps(legacy)))
    store=IncidentStore(tmp_path)
    assert store.list()==[legacy]
    assert store.list(analysis_id='new-video')==[]
    # Filtering occurs before the history display limit, and metadata survives updates.
    for n in range(205):
        store.save({'incident_id':str(n),'created_at':f'2026-02-{n:03}', 'analysis_id':'other-video'})
    store.save({'incident_id':'chosen','created_at':'2026-01-02','analysis_id':'chosen-video','evidence_status':'CAPTURING'})
    assert [r['incident_id'] for r in store.list(analysis_id='chosen-video')]==['chosen']
    store.save({'incident_id':'chosen','created_at':'2026-01-02','analysis_id':'chosen-video','evidence_status':'SAVED'})
    assert store.list(analysis_id='chosen-video')[0]['evidence_status']=='SAVED'
    assert len(store.list(analysis_id='other-video'))==200


def test_upload_selection_survives_navigation_and_can_be_cleared(monkeypatch,tmp_path):
    import src.incidents.manager as module
    store=IncidentStore(tmp_path/'incidents')
    monkeypatch.setattr(module,'IncidentStore',lambda:store)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    app.segmented_control[0].set_value('UPLOAD VIDEO').run()
    app.session_state['saved_upload']={'path':str(ROOT/'data/simulations/normal.mp4'),'name':'my-drive.mp4'}
    app.run()
    selected=app.session_state['selected_source']
    app.radio[0].set_value('Incidents').run()
    assert any('my-drive.mp4' in e.value for e in app.caption)
    app.radio[0].set_value('Live Analysis').run()
    assert app.segmented_control[0].value=='UPLOAD VIDEO'
    assert app.session_state['selected_source']==selected
    # Another UI rerun must not clear an upload merely because its widget was recreated.
    app.run()
    assert app.session_state['selected_source']==selected
    next(b for b in app.button if b.label=='Clear selected video').click().run()
    assert app.session_state['selected_source'] is None
    app.radio[0].set_value('Incidents').run()
    assert not app.exception
    assert any('Select a video' in e.value for e in app.info)
