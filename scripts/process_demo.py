import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config.settings import ROOT
from src.video_processor import process_video
import json, shutil
out=ROOT/'outputs/demo'
s=process_video(ROOT/'data/demo/traffic.mp4',out,device='cpu',max_seconds=35,progress=lambda p,n,r: print(f'{p:.0%} | {n} frames | risk {r}',flush=True))
shutil.copy2(out/'processed.mp4',ROOT/'outputs/demo_processed.mp4')
print(json.dumps({k:v for k,v in s.items() if k not in ('timeline','events')},indent=2))
