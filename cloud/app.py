"""Streamlit Community Cloud entry point: cached video, no hosted inference/uploads."""
import os,sys,runpy
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
os.environ['CRASHZERO_HOSTED']='1'
runpy.run_path(str(root/'app.py'),run_name='__main__')
