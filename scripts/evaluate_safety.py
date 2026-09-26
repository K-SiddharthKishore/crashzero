"""Deterministic synthetic engineering evaluation; never a real-world accuracy claim."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
from src.video.simulation import SCENARIOS,scene
from src.safety.verifier import CrashVerifier
from src.trajectory import TrajectoryStore
from src.conflicts import detect_conflicts
from src.events import EventManager
from config.settings import ROOT

def evaluate():
    rows=[]
    for name in SCENARIOS:
        store=TrajectoryStore();verifier=CrashVerifier();events=EventManager();results=[]
        for k in range(144):
            t=k/12;tracks=store.update(scene(name,t),t);interactions=detect_conflicts(tracks)
            events.update(interactions,tracks,t);results.extend(verifier.update(tracks,interactions,t))
        events.flush(t)
        likely=[r for r in results if r['state'].startswith('LIKELY')]
        rows.append({'scenario':name,'expected_likely':name in ('collision','single_bike'),
            'likely_events':len(likely),'final_states':[r['state'] for r in results],
            'near_misses':sum(e['status']=='prototype near miss' for e in events.events)})
    return {'scope':'SYNTHETIC SCRIPTED TRACKS ONLY — bypasses YOLO; no real-world accuracy claim',
        'true_positives':sum(r['expected_likely'] and r['likely_events']>0 for r in rows),
        'false_positives':sum(not r['expected_likely'] and r['likely_events']>0 for r in rows),
        'false_negatives':sum(r['expected_likely'] and r['likely_events']==0 for r in rows),'scenarios':rows}
if __name__=='__main__':
    report=evaluate();out=ROOT/'outputs/safety_evaluation.json';out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
