"""Explicit local-only launcher. Does not enable either call flag automatically."""
from pathlib import Path
import os
import subprocess
import sys
from dotenv import load_dotenv
root=Path(__file__).resolve().parents[1]
load_dotenv(root/'.env',override=False)
os.environ['CRASHZERO_LOCAL_CALLS']='true'
if any(os.getenv(k)=='1' for k in ('CRASHZERO_V2_HOSTED','CRASHZERO_HOSTED')):
    raise SystemExit('Hosted real calling is forbidden.')
mode=sys.argv[1] if len(sys.argv)>1 else 'ui'
if mode=='callbacks':
    command=[sys.executable,'-m','uvicorn','src.alerts.callbacks:app','--host','127.0.0.1','--port','8765','--no-access-log']
elif mode=='ui':
    command=[sys.executable,'-m','streamlit','run','app.py','--server.address','127.0.0.1','--server.port',os.getenv('PORT','8501')]
else: raise SystemExit('Use ui or callbacks.')
raise SystemExit(subprocess.call(command,cwd=root))
